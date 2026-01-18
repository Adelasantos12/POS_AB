release: python manage.py migrate && python manage.py setup_roles && python manage.py collectstatic --noinput
web: gunicorn adele_pos.wsgi --log-file -
