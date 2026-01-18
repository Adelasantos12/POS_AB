release: python manage.py migrate && python manage.py collectstatic --noinput
web: gunicorn adele_pos.wsgi --log-file -
