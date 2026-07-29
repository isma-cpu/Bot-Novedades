import os
import sys
import json
import time
import requests
from io import BytesIO
from datetime import datetime
from bs4 import BeautifulSoup
from PIL import Image
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ================= CONFIGURACIÓ =================
YUPOO_URL = "https://wavesoccer.x.yupoo.com/albums/7069514?uid=1&isSubCate=false&referrercate=2918263"
FOLDER_NAME_DRIVE = "Novedades"
CREDENTIALS_DICT = json.loads(os.environ.get("GCP_SA_KEY", "{}"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ================= INICIALITZACIÓ =================
genai.configure(api_key=GEMINI_API_KEY)
# Utilitzem la versió 'latest' per evitar errors 404 de servidor
vision_model = genai.GenerativeModel('gemini-1.5-flash-latest') 

def get_drive_service():
    creds = service_account.Credentials.from_service_account_info(
        CREDENTIALS_DICT, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def get_folder_id(service, folder_name, parent_id=None):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

def create_folder(service, folder_name, parent_id=None):
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        folder_metadata['parents'] = [parent_id]
    folder = service.files().create(body=folder_metadata, fields='id').execute()
    return folder.get('id')

def get_or_create_state_file(service, parent_id):
    query = f"name='processed_urls.json' and '{parent_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id)").execute()
    
    if results.get('files'):
        file_id = results['files'][0]['id']
        content = service.files().get_media(fileId=file_id).execute()
        return json.loads(content.decode('utf-8')), file_id
    else:
        return [], None

def update_state_file(service, parent_id, file_id, data):
    media = MediaIoBaseUpload(BytesIO(json.dumps(data).encode('utf-8')), mimetype='application/json')
    if file_id:
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        metadata = {'name': 'processed_urls.json', 'parents': [parent_id]}
        service.files().create(body=metadata, media_body=media).execute()

def is_frontal_view(image_bytes):
    try:
        img = Image.open(BytesIO(image_bytes))
        prompt = """Eres un experto en equipaciones de fútbol. 
        Analiza esta imagen y responde SOLO con la palabra 'SI' si es la vista FRONTAL de una camiseta de fútbol (se ve el pecho, escudo o logo principal). 
        Responde 'NO' si es la parte trasera, un detalle del tejido, una etiqueta, pantalones solos o cualquier otra cosa."""
        
        response = vision_model.generate_content([prompt, img])
        return 'SI' in response.text.upper()
    except Exception as e:
        print(f"⚠️ Error analitzant imatge amb IA: {e}")
        return False

def scrape_yupoo_album():
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(YUPOO_URL, headers=headers)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    images = soup.find_all('img')
    urls = []
    for img in images:
        src = img.get('data-origin-src') or img.get('src')
        if src and ('yupoo' in src or 'photo' in src):
            if not src.startswith('http'):
                src = 'https:' + src
            urls.append(src)
    return urls

def main():
    print("Iniciant automatització...")
    try:
        service = get_drive_service()
        
        root_folder_id = get_folder_id(service, FOLDER_NAME_DRIVE)
        if not root_folder_id:
            print(f"❌ ¡Error! No s'ha trobat la carpeta '{FOLDER_NAME_DRIVE}'.")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        today_folder_id = get_folder_id(service, today_str, root_folder_id)
        if not today_folder_id:
            today_folder_id = create_folder(service, today_str, root_folder_id)

        processed_urls, state_file_id = get_or_create_state_file(service, root_folder_id)

        all_urls = scrape_yupoo_album()
        new_urls = [u for u in all_urls if u not in processed_urls]
        
        print(f"Trobades {len(new_urls)} imatges noves pendents de processar.")
        
        procesadas_hoy = 0
        descartadas = 0
        
        # Simulem ser un navegador real perquè Yupoo no ens bloquegi
        headers = {'Referer': 'https://yupoo.com/', 'User-Agent': 'Mozilla/5.0'}
        
        for idx, url in enumerate(new_urls):
            print(f"Analitzant imatge {idx+1}/{len(new_urls)}...")
            try:
                r = requests.get(url, headers=headers, timeout=15)
                
                # Comprovem que ens ha descarregat una imatge real i no una web d'error
                if r.status_code == 200 and 'image' in r.headers.get('Content-Type', '').lower():
                    if is_frontal_view(r.content):
                        filename = f"camiseta_frontal_{today_str}_{idx}.jpg"
                        media = MediaIoBaseUpload(BytesIO(r.content), mimetype='image/jpeg', resumable=True)
                        file_metadata = {'name': filename, 'parents': [today_folder_id]}
                        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                        procesadas_hoy += 1
                        print(f"✅ ¡Frontal detectada! Pujada com {filename}")
                    else:
                        descartadas += 1
                        print("❌ No és frontal. Descartada.")
                else:
                    print(f"⚠️ La web no ha retornat una imatge vàlida. Status: {r.status_code}")
                
                # Afegim l'URL a l'historial encara que hagi fallat, per no encallar-nos demà
                processed_urls.append(url)
                time.sleep(2) # Pausa necessària per no saturar l'API
                
            except Exception as e:
                print(f"Error descarregant URL {idx+1}: {e}")
        
        # Desem l'historial finalment i creem el text
        print("Guardant registre de memòria i text de TikTok a Drive...")
        if procesadas_hoy > 0:
            texto_tiktok = f"NOVEDADES ({today_str})\n\n¡Nuevas camisetas disponibles! Link en bio 🔥👕⚽\n#camisetasdefutbol #novedades"
            media_txt = MediaIoBaseUpload(BytesIO(texto_tiktok.encode('utf-8')), mimetype='text/plain')
            txt_metadata = {'name': f'Descripcion_TikTok_{today_str}.txt', 'parents': [today_folder_id]}
            service.files().create(body=txt_metadata, media_body=media_txt).execute()

        update_state_file(service, root_folder_id, state_file_id, processed_urls)
        print(f"Resum del dia: {procesadas_hoy} pujades, {descartadas} descartades.")
        
    except Exception as e:
        print(f"❌ Error crític general a l'script: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
