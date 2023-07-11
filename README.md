## Solve Logistics JRM backend

### Development
* Starting up the server:
  1. Go to the `docker/dev` directory 
  2. If you're doing initialization, execute first: `docker-compose run --entrypoint "/bin/sh -c 'python manage.py migrate && python manage.py createsuperuser'" django`
  3. Then this (for testing purposes): `docker-compose run --entrypoint "python manage.py loaddata fixtures/test.json" django`
  4. Run it in isolated Docker environment using: `docker-compose up` (add `-d` parameter if you want to run it in the background)