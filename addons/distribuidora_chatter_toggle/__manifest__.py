{
    'name': "Distribuidora - Chatter colapsable",
    'version': '19.0.1.0.0',
    'category': 'Discuss',
    'summary': "Oculta el chatter por defecto en los formularios y agrega una burbuja flotante para abrirlo/cerrarlo",
    'author': "Distribuidora",
    'depends': ['mail'],
    'assets': {
        'web.assets_backend': [
            'distribuidora_chatter_toggle/static/src/chatter_toggle/chatter_toggle.scss',
            'distribuidora_chatter_toggle/static/src/chatter_toggle/chatter_toggle.js',
            'distribuidora_chatter_toggle/static/src/chatter_toggle/chatter_toggle.xml',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
