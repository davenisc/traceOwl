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

# Function to get geolocation
def get_geolocation(ip):
    url = f"https://api.ipgeolocation.io/ipgeo?apiKey={API_KEY}&ip={ip}"
    response = requests.get(url)
    return response.json()

@app.route('/')
def index():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    geolocation_data = get_geolocation(user_ip)
    # Save or process geolocation data as needed
    print(Fore.GREEN + f"Geolocation for {user_ip}: {geolocation_data}")
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
    global image_url, link_url, page_title

    parser = argparse.ArgumentParser(description='traceOwl Configuration')
    parser.add_argument('--image', type=str, help='URL of the image')
    parser.add_argument('--article', type=str, help='URL of the redirection article')
    parser.add_argument('--title', type=str, help='Title of the webpage')
    parser.add_argument('--apikey', type=str, help='API key for ipgeolocation.io', required=True)

    args = parser.parse_args()

    if args.image:
        image_url = args.image
    if args.article:
        link_url = args.article
    if args.title:
        page_title = args.title
    if args.apikey:
        global API_KEY
        API_KEY = args.apikey

    if not image_url or not link_url or not page_title:
        print(Fore.RED + "ERROR: The URLs for the image, the article, and the title must be set.")
        return

    print(Fore.CYAN + """
        /╲ ︵ ╱\\
        l (◉) (◉)
        \\ ︶ V︶ /
        /↺↺↺↺\\
        ↺↺↺↺↺
        \\↺↺↺↺/
        ¯¯/\\¯/\\¯
    """ + Style.RESET_ALL + Fore.YELLOW + """
        traceOwl - The tool for tracking and raising awareness about suspicious links
    """ + Style.RESET_ALL)

    print(Fore.GREEN + f"Image URL: {image_url}")
    print(Fore.GREEN + f"Redirection URL: {link_url}")
    print(Fore.GREEN + f"Page Title: {page_title}")

    app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    main()
