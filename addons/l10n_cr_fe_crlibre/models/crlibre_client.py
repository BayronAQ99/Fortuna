import base64
import logging
import re
import time

import requests

from odoo import models

_logger = logging.getLogger(__name__)

TIMEOUT = 30
# La API_Hacienda (CRLibre) local a veces devuelve una respuesta HTTP 200 con el
# cuerpo vacio bajo el patron exacto de llamadas que hace este cliente (varias
# peticiones en rafaga, con una llamada real a Hacienda de por medio antes de
# firmar). No se identifico la causa exacta del lado del PHP; es transitorio -
# el mismo request repetido inmediatamente despues normalmente funciona.
RETRY_ATTEMPTS = 3
RETRY_DELAY = 1.5


class CrlibreApiError(Exception):
    """Error al comunicarse con la API_Hacienda de CRLibre."""


class CrlibreFeClient(models.AbstractModel):
    _name = 'l10n_cr.fe.client'
    _description = 'Cliente HTTP para la API_Hacienda (CRLibre)'

    _ENVIRONMENT_URLS = {
        'stag': ('https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token', 'api-stag'),
        'prod': ('https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token', 'api-prod'),
    }

    _CLIENT_ID_BY_ENVIRONMENT = {'stag': 'api-stag', 'prod': 'api-prod'}

    def _get_base_url(self):
        url = self.env['ir.config_parameter'].sudo().get_param('l10n_cr_fe.api_url')
        if not url:
            raise CrlibreApiError("Falta configurar 'l10n_cr_fe.api_url'.")
        return url.rstrip('/')

    def _call(self, w, r, params):
        # POST con datos en el body: algunos parametros (XML firmado, certificado en
        # base64) son demasiado grandes para una URL y provocan HTTP 414 si se envian
        # como query string (ver clave/firmarXML/genXML/send). La API lee 'w' de
        # $_POST o $_GET indistintamente (www/api.php), asi que POST funciona para
        # todas las llamadas de este metodo.
        payload = dict(params or {})
        payload['w'] = w
        payload['r'] = r
        url = self._get_base_url() + '/api.php'
        error = None
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                resp = requests.post(url, data=payload, timeout=TIMEOUT)
            except requests.RequestException as exc:
                error = CrlibreApiError("No se pudo conectar con la API: %s" % exc)
            else:
                if resp.status_code != 200:
                    raise CrlibreApiError("La API respondió HTTP %s" % resp.status_code)
                try:
                    data = resp.json()
                except ValueError:
                    error = CrlibreApiError("La API devolvió una respuesta no-JSON.")
                else:
                    # La API envuelve todo en {"status": "...", "resp": <datos>} (ver Task 1 / api-samples.md)
                    if not isinstance(data, dict) or data.get('status') != 'ok':
                        raise CrlibreApiError("La API respondió estado no-ok: %s" % data)
                    return data.get('resp')
            if attempt < RETRY_ATTEMPTS:
                _logger.warning(
                    "CRLibre API: intento %s/%s fallido para %s/%s (%s), reintentando...",
                    attempt, RETRY_ATTEMPTS, w, r, error)
                time.sleep(RETRY_DELAY)
        raise error

    def get_clave(self, params):
        resp = self._call('clave', 'clave', params)
        if not isinstance(resp, dict) or not resp.get('clave'):
            raise CrlibreApiError("Respuesta inesperada de 'clave': %s" % resp)
        return {'clave': resp['clave'], 'consecutivo': resp.get('consecutivo', '')}

    def gen_xml_fe(self, params):
        resp = self._call('genXML', 'gen_xml_fe', params)
        if not isinstance(resp, dict) or not resp.get('xml'):
            raise CrlibreApiError("Respuesta inesperada de 'gen_xml_fe': %s" % resp)
        return base64.b64decode(resp['xml']).decode('utf-8')

    def gen_xml_nc(self, params):
        resp = self._call('genXML', 'gen_xml_nc', params)
        if not isinstance(resp, dict) or not resp.get('xml'):
            raise CrlibreApiError("Respuesta inesperada de 'gen_xml_nc': %s" % resp)
        return base64.b64decode(resp['xml']).decode('utf-8')

    def gen_xml_nd(self, params):
        resp = self._call('genXML', 'gen_xml_nd', params)
        if not isinstance(resp, dict) or not resp.get('xml'):
            raise CrlibreApiError("Respuesta inesperada de 'gen_xml_nd': %s" % resp)
        return base64.b64decode(resp['xml']).decode('utf-8')

    def gen_xml_te(self, params):
        resp = self._call('genXML', 'gen_xml_te', params)
        if not isinstance(resp, dict) or not resp.get('xml'):
            raise CrlibreApiError("Respuesta inesperada de 'gen_xml_te': %s" % resp)
        return base64.b64decode(resp['xml']).decode('utf-8')

    def gen_xml_mr(self, params):
        resp = self._call('genXML', 'gen_xml_mr', params)
        if not isinstance(resp, dict) or not resp.get('xml'):
            raise CrlibreApiError("Respuesta inesperada de 'gen_xml_mr': %s" % resp)
        return base64.b64decode(resp['xml']).decode('utf-8')

    def register_api_user(self, full_name, username, password):
        resp = self._call('users', 'users_register', {
            'fullName': full_name,
            'userName': username,
            'email': '%s@l10n-cr-fe.local' % username,
            'about': 'Cuenta de servicio Odoo l10n_cr_fe_crlibre',
            'country': 'crc',
            'pwd': password,
        })
        if not isinstance(resp, dict) or not resp.get('sessionKey'):
            raise CrlibreApiError("Respuesta inesperada de 'users_register': %s" % resp)
        return {'session_key': resp['sessionKey'], 'id_user': resp.get('idUser')}

    def login_api_user(self, username, password):
        resp = self._call('users', 'users_log_me_in', {
            'userName': username,
            'pwd': password,
        })
        if not isinstance(resp, dict) or not resp.get('sessionKey'):
            raise CrlibreApiError("Respuesta inesperada de 'users_log_me_in': %s" % resp)
        return {'session_key': resp['sessionKey'], 'id_user': resp.get('idUser')}

    def _call_multipart(self, w, r, params, files):
        query = dict(params or {})
        query['w'] = w
        query['r'] = r
        url = self._get_base_url() + '/api.php'
        try:
            resp = requests.post(url, params=query, files=files, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise CrlibreApiError("No se pudo conectar con la API: %s" % exc)
        if resp.status_code != 200:
            raise CrlibreApiError("La API respondió HTTP %s" % resp.status_code)
        try:
            data = resp.json()
        except ValueError:
            raise CrlibreApiError("La API devolvió una respuesta no-JSON.")
        if not isinstance(data, dict) or data.get('status') != 'ok':
            raise CrlibreApiError("La API respondió estado no-ok: %s" % data)
        return data.get('resp')

    def upload_certificate(self, session_key, username, p12_bytes):
        resp = self._call_multipart('fileUploader', 'subir_certif', {
            'iam': username,
            'sessionKey': session_key,
        }, files={'fileToUpload': ('certificado.p12', p12_bytes, 'application/x-pkcs12')})
        if not isinstance(resp, dict) or not resp.get('downloadCode'):
            raise CrlibreApiError("Respuesta inesperada de 'subir_certif': %s" % resp)
        return {'download_code': resp['downloadCode']}

    def get_hacienda_token(self, username, password, environment):
        idp_url, client_id = self._ENVIRONMENT_URLS[environment]
        resp = self._call('token', 'gettoken', {
            'url': idp_url,
            'grant_type': 'password',
            'client_id': client_id,
            'client_secret': '',
            'username': username,
            'password': password,
        })
        if not isinstance(resp, dict) or not resp.get('access_token'):
            raise CrlibreApiError("Respuesta inesperada de 'token/gettoken': %s" % resp)
        return resp['access_token']

    def sign_xml(self, download_code, pin, xml):
        xml_b64 = base64.b64encode(xml.encode('utf-8')).decode('ascii')
        resp = self._call('firmarXML', 'firmar', {
            'p12Url': download_code,
            'pinP12': pin,
            'inXml': xml_b64,
        })
        if not isinstance(resp, dict) or not resp.get('xmlFirmado'):
            raise CrlibreApiError("Respuesta inesperada de 'firmarXML/firmar': %s" % resp)
        return base64.b64decode(resp['xmlFirmado']).decode('utf-8')

    _STATUS_LINE_RE = re.compile(r'^HTTP/\S+\s+(\d+)')

    def _parse_send_response(self, resp, r):
        # La API_Hacienda no envuelve esto en {"httpStatus":..,"text":[...]} - el
        # framework PHP descarta el codigo de estado y solo reenvia la lista cruda
        # de la linea de estado + headers HTTP de la respuesta real de Hacienda
        # (ver tools_reply en api/core/tools.php). Hay que parsear el codigo de la
        # primera linea ("HTTP/2 202 ...") nosotros mismos.
        if not isinstance(resp, list) or not resp:
            raise CrlibreApiError("Respuesta inesperada de 'send/%s': %s" % (r, resp))
        match = self._STATUS_LINE_RE.match(resp[0])
        if not match:
            raise CrlibreApiError("Respuesta inesperada de 'send/%s': %s" % (r, resp))
        http_status = int(match.group(1))
        if http_status not in (200, 202):
            raise CrlibreApiError("Hacienda rechazó el envío (HTTP %s): %s" % (http_status, resp))
        return {'http_status': http_status, 'raw': resp}

    def send_fe(self, token, clave, fecha_iso, emisor_tipo, emisor_num,
                receptor_tipo, receptor_num, xml_firmado, environment):
        resp = self._call('send', 'json', {
            'token': token,
            'clave': clave,
            'fecha': fecha_iso,
            'emi_tipoIdentificacion': emisor_tipo,
            'emi_numeroIdentificacion': emisor_num,
            'recp_tipoIdentificacion': receptor_tipo,
            'recp_numeroIdentificacion': receptor_num,
            'comprobanteXml': base64.b64encode(xml_firmado.encode('utf-8')).decode('ascii'),
            'client_id': self._CLIENT_ID_BY_ENVIRONMENT[environment],
        })
        return self._parse_send_response(resp, 'json')

    def send_mr(self, token, clave, fecha_iso, emisor_tipo, emisor_num,
                receptor_tipo, receptor_num, consecutivo_receptor, xml_firmado, environment):
        resp = self._call('send', 'sendMensaje', {
            'token': token,
            'clave': clave,
            'fecha': fecha_iso,
            'emi_tipoIdentificacion': emisor_tipo,
            'emi_numeroIdentificacion': emisor_num,
            'recp_tipoIdentificacion': receptor_tipo,
            'recp_numeroIdentificacion': receptor_num,
            'consecutivoReceptor': consecutivo_receptor,
            'comprobanteXml': base64.b64encode(xml_firmado.encode('utf-8')).decode('ascii'),
            'client_id': self._CLIENT_ID_BY_ENVIRONMENT[environment],
        })
        return self._parse_send_response(resp, 'sendMensaje')

    def consultar_estado(self, token, clave, environment):
        resp = self._call('consultar', 'consultarCom', {
            'token': token,
            'clave': clave,
            'client_id': self._CLIENT_ID_BY_ENVIRONMENT[environment],
        })
        if not isinstance(resp, dict):
            return {'ind_estado': 'desconocido', 'respuesta_xml': None}
        return {
            'ind_estado': resp.get('ind-estado', 'desconocido'),
            'respuesta_xml': resp.get('respuesta-xml'),
        }
