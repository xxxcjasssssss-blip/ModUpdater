import os
import zipfile
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, send_file

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
UPDATED_FOLDER = 'updated_mods'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(UPDATED_FOLDER, exist_ok=True)

MODRINTH_API_URL = "https://api.modrinth.com/v2"

def process_single_mod_file(file_path, filename, target_version, target_loader):
    destination_path = os.path.join(UPDATED_FOLDER, filename)
    download_url = None

    try:
        query = os.path.splitext(filename)[0]
        search_url = f"{MODRINTH_API_URL}/search"
        params = {
            "query": query,
            "facets": f'[["versions:{target_version}"], ["categories:{target_loader}"], ["project_type:mod"]]'
        }
        
        response = requests.get(search_url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            hits = data.get("hits", [])
            if hits:
                project_id = hits[0].get("project_id")
                versions_url = f"{MODRINTH_API_URL}/project/{project_id}/version"
                v_response = requests.get(versions_url, timeout=10)
                if v_response.status_code == 200:
                    versions = v_response.json()
                    for v in versions:
                        if target_version in v.get("game_versions", []) and target_loader in v.get("loaders", []):
                            files = v.get("files", [])
                            if files:
                                download_url = files[0].get("url")
                                break
    except Exception as e:
        print(f"Error processing {filename}: {e}")

    if download_url:
        try:
            r = requests.get(download_url, timeout=15)
            if r.status_code == 200:
                with open(destination_path, 'wb') as f:
                    f.write(r.content)
                return destination_path
        except Exception:
            pass

    try:
        with open(file_path, 'rb') as src, open(destination_path, 'wb') as dst:
            dst.write(src.read())
    except Exception:
        pass
        
    return destination_path

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update-mods', methods=['POST'])
def update_mods():
    target_version = request.form.get('version')
    target_loader = request.form.get('loader')
    uploaded_files = request.files.getlist('mods')

    if not uploaded_files or not target_version or not target_loader:
        return "الرجاء التأكد من رفع الملفات وإدخال الإصدار والمنصة."

    extracted_mod_paths = []

    for file_obj in uploaded_files:
        if file_obj.filename == '':
            continue
            
        filename = file_obj.filename
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file_obj.save(file_path)

        if filename.endswith('.zip'):
            try:
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    for inner_file in zip_ref.namelist():
                        if inner_file.endswith('.jar'):
                            zip_ref.extract(inner_file, UPLOAD_FOLDER)
                            extracted_mod_paths.append({
                                'path': os.path.join(UPLOAD_FOLDER, inner_file),
                                'name': os.path.basename(inner_file)
                            })
            except Exception as e:
                print(f"Error extracting zip {filename}: {e}")
        elif filename.endswith('.jar'):
            extracted_mod_paths.append({
                'path': file_path,
                'name': filename
            })

    if not extracted_mod_paths:
        return "لم يتم العثور على ملفات مودات صالحة."

    processed_files = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(process_single_mod_file, item['path'], item['name'], target_version, target_loader): item['name'] 
            for item in extracted_mod_paths
        }
        
        for future in as_completed(futures):
            res = future.result()
            if res:
                processed_files.append(res)

    output_zip_path = os.path.join(UPDATED_FOLDER, f"updated_mods_{target_version}_{target_loader}.zip")
    with zipfile.ZipFile(output_zip_path, 'w') as zipf:
        for file in processed_files:
            zipf.write(file, os.path.basename(file))

    return send_file(output_zip_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)