# Splunkbase-Download-script
Python Script for downloading Splunk Apps from Splunkbase
Important:
You need both files: 1) login.json for your credentials 2) Your_apps.json to dertermine wich apps should be downloaded. 
The "uid" and "version" fields are the most important ones !


login.json
```
  {
      "username": "Dein Splunk.com Loginname Oder Mail-Adresse",
      "password": "Dein Splunk.com Passwort"
  }
```

Your_apps.json
```
[
  {
      "name": "Splunk Add-on for Microsoft Windows",
      "uid": 742,
      "appid": "Splunk_TA_windows",
      "updated_time": "Tue, 26 Sep 2023 06:23:01 GMT",
      "version": "8.8.0"
  },
  {
      "name": "Splunk Common Information Model (CIM)",
      "uid": 1621,
      "appid": "Splunk_SA_CIM",
      "updated_time": "Wed, 08 Nov 2023 21:06:39 GMT",
      "version": "5.1.2"
  },
  {
      "name": "Splunk Add-on for Unix and Linux",
      "uid": 833,
      "appid": "Splunk_TA_nix",
      "updated_time": "Wed, 08 Nov 2023 19:23:49 GMT",
      "version": "9.0.0"
  }
]
```

