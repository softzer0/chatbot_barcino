## Chatbot

### Development
* Starting up the server:
  1. Go to the `docker/dev` directory 
  2. If you're doing initialization, execute first: `docker-compose run --entrypoint "/bin/sh -c 'python manage.py migrate && python manage.py createsuperuser'" django`
  3. Then this (for testing purposes): `docker-compose run --entrypoint "python manage.py loaddata fixtures/barcino.json" django`
  4. Run it in isolated Docker environment using: `docker-compose up` (add `-d` parameter if you want to run it in the background)

### Production
You would need some Debian/Ubuntu distribution for the following:
1. Install Git:
    ```bash
    sudo apt-get update
    sudo apt-get install git
    ```
2. Generate SSH Key:
    ```bash
    ssh-keygen -t ed25519 -C "your_email@example.com"
    ```
    Email must be the one used for your GitHub account.
3. You need to copy the SSH public key that you just generated to your GitHub account. Display the key with the following command, then copy the output:
    ```bash
    cat ~/.ssh/id_ed25519.pub
    ```
4. In your GitHub account, go to Settings -> SSH and GPG keys -> New SSH Key. Paste the copied public key into the Key field and add a title. Click Add SSH key.
5. Open the SSH configuration file in your favorite text editor:
    ```bash
    nano ~/.ssh/config
    ```
    Add the following lines:
    ```bash
    Host github.com
        IdentityFile ~/.ssh/id_ed25519
        IdentitiesOnly yes
    ```
    Save and close the file.
6. To start the ssh-agent in the background, run:
    ```bash
    eval "$(ssh-agent -s)"
    ```
7. Then, add your SSH private key to the ssh-agent:
    ```bash
    ssh-add ~/.ssh/id_ed25519
    ```
   Now your host is ready for GitHub Actions. Next, clone this repository:
   ```bash
   git clone git@github.com:softzer0/chatbot.git
   ```
8. You can proceed to execute `docker/dev/prod/setup.sh` and it will install and setup Nginx with running project in Docker.