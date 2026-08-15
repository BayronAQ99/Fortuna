import requests

from odoo import models

ACTIVITY_URL = 'https://api.hacienda.go.cr/fe/ae'
TIMEOUT = 15


class ActivityApiError(Exception):
    """Error al consultar las actividades económicas registradas de un contribuyente en Hacienda."""


class ActivityClient(models.AbstractModel):
    _name = 'l10n_cr.fe.activity.client'
    _description = 'Cliente HTTP para actividades económicas de Hacienda (por cédula)'

    def buscar(self, cedula):
        cedula = (cedula or '').strip()
        if not cedula:
            raise ActivityApiError("Debe indicar la cédula del cliente para buscar sus actividades económicas.")
        try:
            resp = requests.get(ACTIVITY_URL, params={'identificacion': cedula}, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise ActivityApiError("No se pudo conectar con la API de Hacienda: %s" % exc)
        if resp.status_code != 200:
            raise ActivityApiError("La API de Hacienda respondió HTTP %s" % resp.status_code)
        try:
            data = resp.json()
        except ValueError:
            raise ActivityApiError("La API de Hacienda devolvió una respuesta no-JSON.")
        return self._normalizar(data)

    def _normalizar(self, data):
        if not isinstance(data, dict) or 'actividades' not in data:
            raise ActivityApiError("Respuesta inesperada de la API de Hacienda: %s" % data)
        resultados = []
        for item in data['actividades'] or []:
            if not isinstance(item, dict) or not item.get('codigo') or item.get('estado') != 'A':
                continue
            resultados.append({
                'codigo': item['codigo'],
                'descripcion': item.get('descripcion', ''),
            })
        return resultados
