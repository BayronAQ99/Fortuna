from unittest.mock import MagicMock, patch

import requests

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client import ActivityApiError


def _mock_response(status_code=200, json_data=None, raise_json=False):
    resp = MagicMock()
    resp.status_code = status_code
    if raise_json:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = json_data
    return resp


@tagged('post_install', '-at_install')
class TestPartnerActivityClient(TransactionCase):

    def setUp(self):
        super().setUp()
        self.client = self.env['l10n_cr.fe.activity.client']

    def test_buscar_usa_parametro_identificacion(self):
        resp = _mock_response(json_data={
            'nombre': 'ARAR SOCIEDAD ANONIMA',
            'actividades': [
                {'estado': 'A', 'tipo': 'P', 'codigo': '960113',
                 'descripcion': 'PERSONA JURIDICA LEGALMENTE CONSTITUIDAS'},
            ],
        })
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp) as mock_get:
            resultados = self.client.buscar('3101042624')
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.kwargs['params'], {'identificacion': '3101042624'})
        self.assertEqual(resultados, [
            {'codigo': '960113', 'descripcion': 'PERSONA JURIDICA LEGALMENTE CONSTITUIDAS'},
        ])

    def test_buscar_filtra_actividades_inactivas(self):
        resp = _mock_response(json_data={
            'actividades': [
                {'estado': 'A', 'codigo': '561001', 'descripcion': 'Restaurantes'},
                {'estado': 'I', 'codigo': '563001', 'descripcion': 'Bares (inactiva)'},
            ],
        })
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp):
            resultados = self.client.buscar('102340567')
        self.assertEqual(resultados, [{'codigo': '561001', 'descripcion': 'Restaurantes'}])

    def test_buscar_cedula_vacia_lanza_error_sin_llamar_api(self):
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get') as mock_get:
            with self.assertRaises(ActivityApiError):
                self.client.buscar('')
        mock_get.assert_not_called()

    def test_buscar_timeout_lanza_activity_api_error(self):
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    side_effect=requests.exceptions.Timeout()):
            with self.assertRaises(ActivityApiError):
                self.client.buscar('102340567')

    def test_buscar_http_error_lanza_activity_api_error(self):
        resp = _mock_response(status_code=500)
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp):
            with self.assertRaises(ActivityApiError):
                self.client.buscar('102340567')

    def test_buscar_json_invalido_lanza_activity_api_error(self):
        resp = _mock_response(raise_json=True)
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp):
            with self.assertRaises(ActivityApiError):
                self.client.buscar('102340567')

    def test_buscar_respuesta_sin_actividades_lanza_activity_api_error(self):
        resp = _mock_response(json_data={'code': 400, 'status': 'Bad Request'})
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp):
            with self.assertRaises(ActivityApiError):
                self.client.buscar('000000000')

    def test_buscar_sin_actividades_activas_devuelve_lista_vacia(self):
        resp = _mock_response(json_data={'actividades': []})
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp):
            resultados = self.client.buscar('102340567')
        self.assertEqual(resultados, [])
