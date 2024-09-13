On EC2, I suddenly discovered that I couldn't run docker compose -- it complained that I was using some healthcheck feature that wasn't supported in docker engine version 24.

So I found https://linuxiac.com/how-to-install-docker-on-ubuntu-24-04-lts/ which told me how to install a newer docker.  Here's what I did:

    2024-09-13T13:06:41+0000  0:09  sudo apt install apt-transport-https curl
    2024-09-13T13:06:58+0000  0:00  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    2024-09-13T13:07:15+0000  0:01  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    2024-09-13T13:07:23+0000  0:05  sudo apt update
    2024-09-13T13:07:42+0000  0:21  sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

also I hadda do `sudo /etc/init.d/docker start`, which that web page doesn't mention (or I overlooked it).
