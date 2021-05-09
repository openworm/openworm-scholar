from setuptools import setup, find_packages

requires = [
    'plaster_pastedeploy',
    'pyramid >= 1.9a',
    'pyramid_chameleon',
    'pyramid_debugtoolbar',
    'pyramid_retry',
    'pyramid_tm',
    'pyramid_zodbconn',
    'transaction',
    'ZODB3',
    'waitress',
    'arxiv',
    'slackclient',
    'recurrent',
    'python-dateutil',
]

tests_require = [
    'WebTest >= 1.3.1',  # py3 compat
    'pytest',
    'pytest-cov',
]

setup(
    name='ow_scholar',
    version='0.0',
    description='ow-scholar',
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Pyramid',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
    ],
    author='',
    author_email='',
    url='',
    keywords='web pyramid pylons',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    extras_require={
        'testing': tests_require,
    },
    install_requires=requires,
    entry_points={
        'paste.app_factory': [
            'main = ow_scholar:main',
        ],
    },
)
