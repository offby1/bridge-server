logged in as james

http://localhost:9000/hand/313/

AssertionError at /hand/313/
No exception message supplied
Request Method:	GET
Request URL:	http://localhost:9000/hand/313/
Django Version:	5.1.4
Exception Type:	AssertionError
Exception Location:	/Users/not-workme/git-repositories/me/bridge/server/project/app/models/hand.py, line 281, in libPlayers_by_seat
Raised during:	app.views.hand.hand_detail_view
Python Executable:	/Users/not-workme/git-repositories/me/bridge/server/.venv/bin/python
Python Version:	3.13.1
Python Path:
['/Users/not-workme/git-repositories/me/bridge/server/project',
 '/Library/Frameworks/Python.framework/Versions/3.13/lib/python313.zip',
 '/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13',
 '/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/lib-dynload',
 '/Users/not-workme/git-repositories/me/bridge/server/.venv/lib/python3.13/site-packages']
Server time:	Tue, 28 Jan 2025 21:07:46 +0000
Traceback Switch to copy-and-paste view
/Users/not-workme/git-repositories/me/bridge/server/.venv/lib/python3.13/site-packages/django/core/handlers/exception.py, line 42, in inner
                response = await get_response(request)
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^ …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/.venv/lib/python3.13/site-packages/django/core/handlers/base.py, line 253, in _get_response_async
                response = await wrapped_callback(
                                 …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/.venv/lib/python3.13/site-packages/django/contrib/auth/decorators.py, line 60, in _view_wrapper
                    return view_func(request, *args, **kwargs)
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/project/app/views/misc.py, line 79, in non_players_piss_off
            return view_function(request, *args, **kwargs)
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/project/app/views/hand.py, line 535, in hand_detail_view
        hand_is_complete=hand.is_complete,
                              ^^^^^^^^^^^^^^^^ …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/.venv/lib/python3.13/site-packages/django/utils/functional.py, line 47, in __get__
        res = instance.__dict__[self.name] = self.func(instance)
                                                 ^^^^^^^^^^^^^^^^^^^ …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/project/app/models/hand.py, line 605, in is_complete
        x = self.get_xscript()
                 ^^^^^^^^^^^^^^^^^^ …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/project/app/models/hand.py, line 332, in get_xscript
            lib_table = self.lib_table_with_cards_as_dealt
                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/.venv/lib/python3.13/site-packages/django/utils/functional.py, line 47, in __get__
        res = instance.__dict__[self.name] = self.func(instance)
                                                 ^^^^^^^^^^^^^^^^^^^ …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/project/app/models/hand.py, line 288, in lib_table_with_cards_as_dealt
        players = list(self.libPlayers_by_seat.values())
                            ^^^^^^^^^^^^^^^^^^^^^^^ …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/.venv/lib/python3.13/site-packages/django/utils/functional.py, line 47, in __get__
        res = instance.__dict__[self.name] = self.func(instance)
                                                 ^^^^^^^^^^^^^^^^^^^ …
Local vars
/Users/not-workme/git-repositories/me/bridge/server/project/app/models/hand.py, line 281, in libPlayers_by_seat
            assert seat is not None
                        ^^^^^^^^^^^^^^^^ …
Local vars
Request information
USER
james

GET
No GET data

POST
No POST data

FILES
No FILES data

COOKIES
Variable	Value
djdtHeadersPanel
'off'
csrftoken
'********************'
sessionid
'********************'
META
Variable	Value
CSRF_COOKIE
'g1Q6VvHZYmsmEqaKTMvkrMNWoUuUsiaA'
HTTP_ACCEPT
'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
HTTP_ACCEPT_ENCODING
'gzip, deflate, br, zstd'
HTTP_ACCEPT_LANGUAGE
'en-US,en;q=0.9'
HTTP_CACHE_CONTROL
'max-age=0'
HTTP_CONNECTION
'keep-alive'
HTTP_COOKIE
'********************'
HTTP_HOST
'localhost:9000'
HTTP_REFERER
'http://localhost:9000/accounts/login/?next=/hand/313/'
HTTP_SEC_CH_UA
'"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
HTTP_SEC_CH_UA_MOBILE
'?0'
HTTP_SEC_CH_UA_PLATFORM
'"macOS"'
HTTP_SEC_FETCH_DEST
'document'
HTTP_SEC_FETCH_MODE
'navigate'
HTTP_SEC_FETCH_SITE
'same-origin'
HTTP_SEC_FETCH_USER
'?1'
HTTP_UPGRADE_INSECURE_REQUESTS
'1'
HTTP_USER_AGENT
('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, '
 'like Gecko) Chrome/131.0.0.0 Safari/537.36')
PATH_INFO
'/hand/313/'
QUERY_STRING
''
REMOTE_ADDR
'127.0.0.1'
REMOTE_HOST
'127.0.0.1'
REMOTE_PORT
55965
REQUEST_METHOD
'GET'
SCRIPT_NAME
''
SERVER_NAME
'127.0.0.1'
SERVER_PORT
'9000'
wsgi.multiprocess
True
wsgi.multithread
True
Settings
Using settings module project.dev_settings
Setting	Value
ABSOLUTE_URL_OVERRIDES
{}
ADMINS
[]
ALLOWED_HOSTS
['.offby1.info', '.orb.local', '.tail571dc2.ts.net', '127.0.0.1', 'localhost']
API_SKELETON_KEY
'********************'
APPEND_SLASH
True
APP_NAME
'info.offby1.bridge'
ASGI_APPLICATION
'project.asgi.application'
AUTHENTICATION_BACKENDS
['django.contrib.auth.backends.ModelBackend']
AUTH_PASSWORD_VALIDATORS
'********************'
AUTH_USER_MODEL
'auth.User'
BASE_DIR
PosixPath('/Users/not-workme/git-repositories/me/bridge/server/project')
CACHES
{'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
             'LOCATION': 'bridge_django_cache'}}
CACHE_MIDDLEWARE_ALIAS
'default'
CACHE_MIDDLEWARE_KEY_PREFIX
'********************'
CACHE_MIDDLEWARE_SECONDS
600
CSRF_COOKIE_AGE
31449600
CSRF_COOKIE_DOMAIN
None
CSRF_COOKIE_HTTPONLY
False
CSRF_COOKIE_NAME
'csrftoken'
CSRF_COOKIE_PATH
'/'
CSRF_COOKIE_SAMESITE
'Lax'
CSRF_COOKIE_SECURE
False
CSRF_FAILURE_VIEW
'django.views.csrf.csrf_failure'
CSRF_HEADER_NAME
'HTTP_X_CSRFTOKEN'
CSRF_TRUSTED_ORIGINS
[]
CSRF_USE_SESSIONS
False
DATABASES
{'default': {'ATOMIC_REQUESTS': False,
             'AUTOCOMMIT': True,
             'CONN_HEALTH_CHECKS': False,
             'CONN_MAX_AGE': 0,
             'ENGINE': 'django.db.backends.postgresql',
             'HOST': 'localhost',
             'NAME': 'bridge',
             'OPTIONS': {},
             'PASSWORD': '********************',
             'PORT': '',
             'TEST': {'CHARSET': None,
                      'COLLATION': None,
                      'MIGRATE': True,
                      'MIRROR': None,
                      'NAME': None},
             'TIME_ZONE': None,
             'USER': 'postgres'}}
DATABASE_ROUTERS
[]
DATA_UPLOAD_MAX_MEMORY_SIZE
2621440
DATA_UPLOAD_MAX_NUMBER_FIELDS
1000
DATA_UPLOAD_MAX_NUMBER_FILES
100
DATETIME_FORMAT
'N j, Y, P'
DATETIME_INPUT_FORMATS
['%Y-%m-%d %H:%M:%S',
 '%Y-%m-%d %H:%M:%S.%f',
 '%Y-%m-%d %H:%M',
 '%m/%d/%Y %H:%M:%S',
 '%m/%d/%Y %H:%M:%S.%f',
 '%m/%d/%Y %H:%M',
 '%m/%d/%y %H:%M:%S',
 '%m/%d/%y %H:%M:%S.%f',
 '%m/%d/%y %H:%M']
DATE_FORMAT
'N j, Y'
DATE_INPUT_FORMATS
['%Y-%m-%d',
 '%m/%d/%Y',
 '%m/%d/%y',
 '%b %d %Y',
 '%b %d, %Y',
 '%d %b %Y',
 '%d %b, %Y',
 '%B %d %Y',
 '%B %d, %Y',
 '%d %B %Y',
 '%d %B, %Y']
DEBUG
True
DEBUG_PROPAGATE_EXCEPTIONS
False
DECIMAL_SEPARATOR
'.'
DEFAULT_AUTO_FIELD
'django.db.models.BigAutoField'
DEFAULT_CHARSET
'utf-8'
DEFAULT_EXCEPTION_REPORTER
'django.views.debug.ExceptionReporter'
DEFAULT_EXCEPTION_REPORTER_FILTER
'django.views.debug.SafeExceptionReporterFilter'
DEFAULT_FROM_EMAIL
'webmaster@localhost'
DEFAULT_INDEX_TABLESPACE
''
DEFAULT_TABLESPACE
''
DEPLOYMENT_ENVIRONMENT
'development'
DISALLOWED_USER_AGENTS
[]
EMAIL_BACKEND
'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST
'localhost'
EMAIL_HOST_PASSWORD
'********************'
EMAIL_HOST_USER
''
EMAIL_PORT
25
EMAIL_SSL_CERTFILE
None
EMAIL_SSL_KEYFILE
'********************'
EMAIL_SUBJECT_PREFIX
'[Django] '
EMAIL_TIMEOUT
None
EMAIL_USE_LOCALTIME
False
EMAIL_USE_SSL
False
EMAIL_USE_TLS
False
EVENTSTREAM_CHANNELMANAGER_CLASS
'app.channelmanager.MyChannelManager'
EVENTSTREAM_STORAGE_CLASS
'django_eventstream.storage.DjangoModelStorage'
FASTDEV_STRICT_IF
True
FILE_UPLOAD_DIRECTORY_PERMISSIONS
None
FILE_UPLOAD_HANDLERS
['django.core.files.uploadhandler.MemoryFileUploadHandler',
 'django.core.files.uploadhandler.TemporaryFileUploadHandler']
FILE_UPLOAD_MAX_MEMORY_SIZE
2621440
FILE_UPLOAD_PERMISSIONS
420
FILE_UPLOAD_TEMP_DIR
None
FIRST_DAY_OF_WEEK
0
FIXTURE_DIRS
[]
FORCE_SCRIPT_NAME
None
FORMAT_MODULE_PATH
None
FORMS_URLFIELD_ASSUME_HTTPS
False
FORM_RENDERER
'django.forms.renderers.DjangoTemplates'
GIT_SYMBOLIC_REF
'refs/heads/ecs'
IGNORABLE_404_URLS
[]
INSTALLED_APPS
['daphne',
 'django_fastdev',
 'django_eventstream',
 'django.contrib.admin',
 'django.contrib.admindocs',
 'django.contrib.auth',
 'django.contrib.contenttypes',
 'django.contrib.sessions',
 'django.contrib.messages',
 'django.contrib.staticfiles',
 'debug_toolbar',
 'django_extensions',
 'template_partials',
 'app']
INTERNAL_IPS
['127.0.0.1']
LANGUAGES
[('af', 'Afrikaans'),
 ('ar', 'Arabic'),
 ('ar-dz', 'Algerian Arabic'),
 ('ast', 'Asturian'),
 ('az', 'Azerbaijani'),
 ('bg', 'Bulgarian'),
 ('be', 'Belarusian'),
 ('bn', 'Bengali'),
 ('br', 'Breton'),
 ('bs', 'Bosnian'),
 ('ca', 'Catalan'),
 ('ckb', 'Central Kurdish (Sorani)'),
 ('cs', 'Czech'),
 ('cy', 'Welsh'),
 ('da', 'Danish'),
 ('de', 'German'),
 ('dsb', 'Lower Sorbian'),
 ('el', 'Greek'),
 ('en', 'English'),
 ('en-au', 'Australian English'),
 ('en-gb', 'British English'),
 ('eo', 'Esperanto'),
 ('es', 'Spanish'),
 ('es-ar', 'Argentinian Spanish'),
 ('es-co', 'Colombian Spanish'),
 ('es-mx', 'Mexican Spanish'),
 ('es-ni', 'Nicaraguan Spanish'),
 ('es-ve', 'Venezuelan Spanish'),
 ('et', 'Estonian'),
 ('eu', 'Basque'),
 ('fa', 'Persian'),
 ('fi', 'Finnish'),
 ('fr', 'French'),
 ('fy', 'Frisian'),
 ('ga', 'Irish'),
 ('gd', 'Scottish Gaelic'),
 ('gl', 'Galician'),
 ('he', 'Hebrew'),
 ('hi', 'Hindi'),
 ('hr', 'Croatian'),
 ('hsb', 'Upper Sorbian'),
 ('hu', 'Hungarian'),
 ('hy', 'Armenian'),
 ('ia', 'Interlingua'),
 ('id', 'Indonesian'),
 ('ig', 'Igbo'),
 ('io', 'Ido'),
 ('is', 'Icelandic'),
 ('it', 'Italian'),
 ('ja', 'Japanese'),
 ('ka', 'Georgian'),
 ('kab', 'Kabyle'),
 ('kk', 'Kazakh'),
 ('km', 'Khmer'),
 ('kn', 'Kannada'),
 ('ko', 'Korean'),
 ('ky', 'Kyrgyz'),
 ('lb', 'Luxembourgish'),
 ('lt', 'Lithuanian'),
 ('lv', 'Latvian'),
 ('mk', 'Macedonian'),
 ('ml', 'Malayalam'),
 ('mn', 'Mongolian'),
 ('mr', 'Marathi'),
 ('ms', 'Malay'),
 ('my', 'Burmese'),
 ('nb', 'Norwegian Bokmål'),
 ('ne', 'Nepali'),
 ('nl', 'Dutch'),
 ('nn', 'Norwegian Nynorsk'),
 ('os', 'Ossetic'),
 ('pa', 'Punjabi'),
 ('pl', 'Polish'),
 ('pt', 'Portuguese'),
 ('pt-br', 'Brazilian Portuguese'),
 ('ro', 'Romanian'),
 ('ru', 'Russian'),
 ('sk', 'Slovak'),
 ('sl', 'Slovenian'),
 ('sq', 'Albanian'),
 ('sr', 'Serbian'),
 ('sr-latn', 'Serbian Latin'),
 ('sv', 'Swedish'),
 ('sw', 'Swahili'),
 ('ta', 'Tamil'),
 ('te', 'Telugu'),
 ('tg', 'Tajik'),
 ('th', 'Thai'),
 ('tk', 'Turkmen'),
 ('tr', 'Turkish'),
 ('tt', 'Tatar'),
 ('udm', 'Udmurt'),
 ('ug', 'Uyghur'),
 ('uk', 'Ukrainian'),
 ('ur', 'Urdu'),
 ('uz', 'Uzbek'),
 ('vi', 'Vietnamese'),
 ('zh-hans', 'Simplified Chinese'),
 ('zh-hant', 'Traditional Chinese')]
LANGUAGES_BIDI
['he', 'ar', 'ar-dz', 'ckb', 'fa', 'ug', 'ur']
LANGUAGE_CODE
'en-us'
LANGUAGE_COOKIE_AGE
None
LANGUAGE_COOKIE_DOMAIN
None
LANGUAGE_COOKIE_HTTPONLY
False
LANGUAGE_COOKIE_NAME
'django_language'
LANGUAGE_COOKIE_PATH
'/'
LANGUAGE_COOKIE_SAMESITE
None
LANGUAGE_COOKIE_SECURE
False
LOCALE_PATHS
[]
LOGGING
{'disable_existing_loggers': False,
 'filters': {'request_id': {'()': 'log_request_id.filters.RequestIDFilter'},
             'require_debug_true_or_environment_staging': {'()': 'app.utils.log.RequireDebugTrueOrEnvironmentStaging'}},
 'formatters': {'verbose': {'datefmt': '%Y-%m-%dT%H:%M:%S%z',
                            'format': '{asctime} {levelname:5} '
                                      'request_id={request_id} '
                                      '{filename}({lineno}) {funcName} '
                                      '{message}',
                            'style': '{'}},
 'handlers': {'console': {'class': 'logging.StreamHandler',
                          'filters': ['require_debug_true_or_environment_staging',
                                      'request_id'],
                          'formatter': 'verbose',
                          'level': 'DEBUG'}},
 'loggers': {'app': {'level': 'DEBUG'},
             'bridge': {'handlers': ['console'], 'level': 'DEBUG'},
             'daphne.http_protocol': {'level': 'INFO'},
             'django.channels.server': {'level': 30},
             'django.core.cache': {'level': 'DEBUG'},
             'django_eventstream': {'handlers': ['console'], 'level': 'DEBUG'},
             'django_eventstream.views': {'level': 'WARNING'},
             'urllib3.connectionpool': {'level': 'INFO'}},
 'root': {'handlers': ['console']},
 'version': 1}
LOGGING_CONFIG
'logging.config.dictConfig'
LOGIN_REDIRECT_URL
'app:player'
LOGIN_URL
'/accounts/login/'
LOGOUT_REDIRECT_URL
None
MANAGERS
[]
MEDIA_ROOT
''
MEDIA_URL
'/'
MESSAGE_STORAGE
'django.contrib.messages.storage.fallback.FallbackStorage'
MIDDLEWARE
['app.middleware.swallow_annoying_exception.SwallowAnnoyingExceptionMiddleware',
 'log_request_id.middleware.RequestIDMiddleware',
 'app.middleware.add_git_commit_hash.AddVersionHeaderMiddleware',
 'debug_toolbar.middleware.DebugToolbarMiddleware',
 'django.middleware.security.SecurityMiddleware',
 'whitenoise.middleware.WhiteNoiseMiddleware',
 'django.contrib.admindocs.middleware.XViewMiddleware',
 'django.contrib.sessions.middleware.SessionMiddleware',
 'django.middleware.common.CommonMiddleware',
 'django.middleware.csrf.CsrfViewMiddleware',
 'django.contrib.auth.middleware.AuthenticationMiddleware',
 'django.contrib.messages.middleware.MessageMiddleware',
 'django.middleware.clickjacking.XFrameOptionsMiddleware']
MIGRATION_MODULES
{}
MONTH_DAY_FORMAT
'F j'
NUMBER_GROUPING
0
PASSWORD_HASHERS
'********************'
PASSWORD_RESET_TIMEOUT
'********************'
PREPEND_WWW
False
ROOT_URLCONF
'project.urls'
SECRET_KEY
'********************'
SECRET_KEY_FALLBACKS
'********************'
SECURE_CONTENT_TYPE_NOSNIFF
True
SECURE_CROSS_ORIGIN_OPENER_POLICY
'same-origin'
SECURE_HSTS_INCLUDE_SUBDOMAINS
False
SECURE_HSTS_PRELOAD
False
SECURE_HSTS_SECONDS
0
SECURE_PROXY_SSL_HEADER
('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_REDIRECT_EXEMPT
[]
SECURE_REFERRER_POLICY
'same-origin'
SECURE_SSL_HOST
None
SECURE_SSL_REDIRECT
False
SERVER_EMAIL
'root@localhost'
SESSION_CACHE_ALIAS
'default'
SESSION_COOKIE_AGE
1209600
SESSION_COOKIE_DOMAIN
None
SESSION_COOKIE_HTTPONLY
True
SESSION_COOKIE_NAME
'sessionid'
SESSION_COOKIE_PATH
'/'
SESSION_COOKIE_SAMESITE
'Lax'
SESSION_COOKIE_SECURE
False
SESSION_ENGINE
'django.contrib.sessions.backends.db'
SESSION_EXPIRE_AT_BROWSER_CLOSE
False
SESSION_FILE_PATH
None
SESSION_SAVE_EVERY_REQUEST
False
SESSION_SERIALIZER
'django.contrib.sessions.serializers.JSONSerializer'
SETTINGS_MODULE
'project.dev_settings'
SHORT_DATETIME_FORMAT
'm/d/Y P'
SHORT_DATE_FORMAT
'm/d/Y'
SIGNING_BACKEND
'django.core.signing.TimestampSigner'
SILENCED_SYSTEM_CHECKS
[]
STATICFILES_DIRS
[]
STATICFILES_FINDERS
['django.contrib.staticfiles.finders.FileSystemFinder',
 'django.contrib.staticfiles.finders.AppDirectoriesFinder']
STATIC_ROOT
PosixPath('/Users/not-workme/git-repositories/me/bridge/server/project/static_root')
STATIC_URL
'/static/'
STORAGES
{'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
TEMPLATES
[{'BACKEND': 'django.template.backends.django.DjangoTemplates',
  'DIRS': [],
  'OPTIONS': {'context_processors': ['app.template.context_processors.stick_that_version_in_there_daddy_O',
                                     'app.template.context_processors.stick_deployment_environment_in_there_daddy_O',
                                     'django.template.context_processors.debug',
                                     'django.template.context_processors.request',
                                     'django.contrib.auth.context_processors.auth',
                                     'django.contrib.messages.context_processors.messages'],
              'debug': True,
              'loaders': [('template_partials.loader.Loader',
                           [('django.template.loaders.cached.Loader',
                             ['django.template.loaders.filesystem.Loader',
                              'django.template.loaders.app_directories.Loader'])])]}}]
TEST_NON_SERIALIZED_APPS
[]
TEST_RUNNER
'django.test.runner.DiscoverRunner'
THOUSAND_SEPARATOR
','
TIME_FORMAT
'P'
TIME_INPUT_FORMATS
['%H:%M:%S', '%H:%M:%S.%f', '%H:%M']
TIME_ZONE
'UTC'
USE_I18N
True
USE_THOUSAND_SEPARATOR
False
USE_TZ
True
USE_X_FORWARDED_HOST
True
USE_X_FORWARDED_PORT
False
VERSION
'6300808 2025-01-27'
WSGI_APPLICATION
'project.wsgi.application'
X_FRAME_OPTIONS
'DENY'
YEAR_MONTH_FORMAT
'F Y'
You’re seeing this error because you have DEBUG = True in your Django settings file. Change that to False, and Django will display a standard page generated by the handler for this status code.

DJDT
