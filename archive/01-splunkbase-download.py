####################################
#### Splunkbase Download Script
#### Erstellung: 21.11.2023
#### letzte Änderung: 10.11.2025
#### Creator: Gotarr
####################################

import requests
import json
import os
import datetime

def download(app_id, app_version, cookies, downloaded_apps, skipped_apps):
    file_name = f"{app_id}_{app_version}.tgz"
    updated_time = None  # Neue Variable für das Aktualisierungsdatum
    
    # Checking if the file already exists
    if not os.path.exists(file_name):
        download_url = f"https://api.splunkbase.splunk.com/api/v2/apps/{app_id}/releases/{app_version}/download/?origin=sb&lead=false"
        response = requests.get(download_url, cookies=cookies)
        if response.status_code == 200:
            with open(file_name, 'wb') as file:
                file.write(response.content)
            downloaded_apps.append(file_name)

            # Annahme: Das Aktualisierungsdatum ist im Header der Antwort verfügbar
            updated_time = response.headers.get("Last-Modified", None)
            if not updated_time:
                # Falls kein Aktualisierungsdatum vorhanden ist, verwende den aktuellen Zeitstempel
                updated_time = datetime.datetime.utcnow().isoformat() + "Z"
        else:
            print(f"Failed to download {file_name}. Status code: {response.status_code}")
    else:
        skipped_apps.append(file_name)

    return updated_time

def update_Your_apps_file(apps_data, uid, new_version, updated_time):
    """
    Update the Your_apps.json file with the new version and updated time of the app.
    :param apps_data: List of app data dictionaries from Your_apps.json.
    :param uid: UID of the app to update.
    :param new_version: New version of the app.
    :param updated_time: Updated time of the app.
    """
    # Find the app in the list and update its version and updated time
    for app in apps_data:
        if app['uid'] == uid:
            app['version'] = new_version
            app['updated_time'] = updated_time
            break
    
    # Write the updated data back to the file
    with open('Your_apps.json', 'w') as file:
        json.dump(apps_data, file, indent=4)

def authenticate():
    with open('login.json', 'r') as file:
        login_data = json.load(file)

    login_url = "https://splunkbase.splunk.com/api/account:login/"
    payload = {
        'username': login_data['username'],
        'password': login_data['password']
    }
    response = requests.post(login_url, data=payload)
    if response.status_code == 200:
        cookies = response.cookies.get_dict()
        return cookies
    else:
        raise Exception(f"Authentication failed with status code: {response.status_code}")

def get_latest_version(uid, cookies):
    url = f"https://splunkbase.splunk.com/api/v1/app/{uid}/release/"
    response = requests.get(url, cookies=cookies)

    if response.status_code == 200:
        data = response.json()
        return data[0]['name']  # Assuming the first version in the list is the latest
    else:
        print(f"Error retrieving app version for {uid}: Status code {response.status_code}")
        return None

# Der Hauptablauf des Skripts
if __name__ == '__main__':
    try:
        # Authenticate and get session cookies
        cookies = authenticate()

        # Read the list of apps to check for updates
        with open('Your_apps.json', 'r') as file:
            apps_data_from_file = json.load(file)

        downloaded_apps = []
        skipped_apps = []

        # Iterate through each app and check if an update is needed
        for app in apps_data_from_file:
            latest_version = get_latest_version(app['uid'], cookies)
            if latest_version and latest_version != app.get('version'):
                updated_time = download(app['uid'], latest_version, cookies, downloaded_apps, skipped_apps)
                if updated_time:
                    # Update the Your_apps.json file with the new version and updated time
                    update_Your_apps_file(apps_data_from_file, app['uid'], latest_version, updated_time)
            else:
                skipped_apps.append(f"{app['uid']}_{app.get('version')}")

        print(f"Downloaded apps: {downloaded_apps}")
        print(f"Skipped apps: {skipped_apps}")

    except Exception as e:
        print(f"An error occurred: {str(e)}")
