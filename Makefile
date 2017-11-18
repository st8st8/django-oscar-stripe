install:
	python setup.py develop
	pip install -r requirements.txt

sandbox: install
	python sandbox/setup.py develop
	-python sandbox/manage.py syncdb --noinput
	python sandbox/manage.py migrate --noinput
	-mkdir sandbox/static
	python sandbox/manage.py collectstatic --noinput
	python sandbox/manage.py oscar_populate_countries

