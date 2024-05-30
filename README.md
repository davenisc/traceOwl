# traceOwl - Geolocation Tracking Tool

traceOwl is a tool designed for educational purposes to demonstrate how geolocation tracking can be conducted using social engineering techniques. This tool is intended to raise awareness about cybersecurity threats and help users understand the importance of security measures and cautious online behavior.

<a href="https://ibb.co/6YRMD2L"><img src="https://i.ibb.co/Q9FgYZt/Captura-de-pantalla-2024-05-30-102111.png" alt="Captura-de-pantalla-2024-05-30-102111" border="0"></a>

# *Features*

* Geolocation tracking of users who click on a shared link.
* Customizable image and redirection URL.
* Educational tool to demonstrate the risks of clicking on suspicious links.

# *Installation*

Prerequisites: 

* Python 3.x
* pip (Python package installer)
* ngrok (for exposing the local server to the internet)
* ipgeolocation.io account (API)

# *Download and Install*

1. Clone the repository:

   ```bash
   git clone https://github.com/davenisc/traceOwl.git
   cd traceOwl

2. Install python venv:

   ```bash
   apt install python3.11-venv

3. Create and activate the virtual environment:

   ```bash
   python -m venv traceOwl_venv
   source traceOwl_venv/bin/activate

4. Install the required libraries:

   ```bash
   pip install -r requirements.txt


# **Usage**

1. Run the main script:

   ```bash
   python traceowl.py --image https://YOUR_URL_IMAGE.jpg --article https://davenisc.com --title "Exciting Article" --apikey YOUR_IPGEOLOCATION_API_KEY --ngrok http://YOUR_NGROK_URL

2. Access the tracking page:

   If you are on the same local network (LAN), open your web browser and navigate to http://127.0.0.1:8000.
   If you want to make the tracking page accessible over the internet, use ngrok.
   
# *Using ngrok*

1. Download and install ngrok:

   Download ngrok from ngrok.com and follow the installation instructions for your operating system.

2. Expose your local server to the internet:

   ```bash
   ngrok http http://localhost:8000

3. Get the public URL:

   After running the above command, ngrok will provide you with a public URL. Share this URL with your test subjects to access the tracking page over the internet.

# *How to Install Ngrok on Linux*

1. Install ngrok via Apt with the following command:

   ```bash
   curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
   | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
   && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
   | sudo tee /etc/apt/sources.list.d/ngrok.list \
   && sudo apt update \
   && sudo apt install ngrok

2. Run the following command to add your authtoken to the default ngrok.yml:

    ```bash
   ngrok config add-authtoken YOUR_NGROK_AUTH_TOKEN


# **Disclaimer**

This tool is intended for educational purposes only. The author is not responsible for any misuse of this tool. Always obtain explicit permission from the owner of the system before conducting any tracking tests.

# *License*

This project is licensed under the MIT License. See the LICENSE file for details.

# *Screenshots*

<a href="https://ibb.co/cgzn9Y4"><img src="https://i.ibb.co/f1mwWDj/imagen-2024-05-30-114851935.png" alt="imagen-2024-05-30-114851935" border="0"></a>

<a href="https://ibb.co/6YRMD2L"><img src="https://i.ibb.co/Q9FgYZt/Captura-de-pantalla-2024-05-30-102111.png" alt="Captura-de-pantalla-2024-05-30-102111" border="0"></a>

<a href="https://ibb.co/R2dVPPH"><img src="https://i.ibb.co/XXMvppJ/Captura-de-pantalla-2024-05-30-102244.png" alt="Captura-de-pantalla-2024-05-30-102244" border="0"></a>

# **Credits**
Developer: @davenisc
Web: https://davenisc.com

# *Support*
If you find this project useful, you can support me on Buy Me a Coffee.

<a href="https://buymeacoffee.com/davenisc" target="_blank">
    <img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black" alt="Buy Me a Coffee">
</a>

# **Follow Me**

# *Follow me on my social media profiles:*

<a href="https://twitter.com/davenisc" target="_blank">
    <img src="https://img.shields.io/badge/X-1DA1F2?style=for-the-badge&logo=twitter&logoColor=white" alt="Twitter">
</a>
<a href="https://www.instagram.com/davenisc.co/" target="_blank">
    <img src="https://img.shields.io/badge/Instagram-E4405F?style=for-the-badge&logo=instagram&logoColor=white" alt="Instagram">
</a>
<a href="https://www.linkedin.com/in/davenisc/" target="_blank">
    <img src="https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn">
</a>

# *Donate USDT* 

If you would like to support this project with a USDT BEP-20 donation, you can send it to the following Binance wallet address:

   ```bash
   0x15283841da6b5099d991fd64fdcb302478f4cc5a
