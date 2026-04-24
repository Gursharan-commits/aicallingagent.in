import os

apps = ['tenants', 'users', 'campaigns', 'calls', 'billing', 'ai_engine', 'websockets']

for app in apps:
    path = f'apps/{app}/apps.py'
    if os.path.exists(path):
        with open(path, 'r') as f:
            content = f.read()
        
        content = content.replace(f"name = '{app}'", f"name = 'apps.{app}'")
        
        with open(path, 'w') as f:
            f.write(content)
