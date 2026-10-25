{
    'name': "Distribuidora - Sidebar de navegación",
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': "Reemplaza el selector de apps del navbar por un sidebar fijo y navegable",
    'author': "Distribuidora",
    'depends': ['web'],
    'assets': {
        'web.assets_backend': [
            'distribuidora_sidebar/static/src/sidebar/sidebar.scss',
            'distribuidora_sidebar/static/src/sidebar/sidebar.js',
            'distribuidora_sidebar/static/src/sidebar/sidebar.xml',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
