import os
import sys
import shutil
import zipfile
import tarfile
import importlib
import argparse
import subprocess
import urllib.request
from pathlib import Path

REQUIRED_PACKAGES = {  # import name: pip name
    'yaml': 'PyYAML',
    'kaggle': 'kaggle',
    'dotenv': 'python-dotenv',
    'nbconvert': 'nbconvert'
}

# Install the required packages which do not exist
for import_name, pip_name in REQUIRED_PACKAGES.items():
    try:
        importlib.import_module(import_name)
    except ImportError:
        print(f'[EnvKit] Info: Installing {pip_name}...')
        subprocess.run([sys.executable, '-m', 'pip', 'install', pip_name], check=True)

import yaml
from dotenv import load_dotenv

# --------------------------------------------------

def install_packages(config):
    packages = config.get('packages', [])
    if not packages:
        print('[EnvKit] Info: No package installation tasks found')
        return
    if isinstance(packages, str):
        packages = [packages]

    print(f'[EnvKit] Info: Installing {len(packages)} packages...')
    
    cmd = [sys.executable, '-m', 'pip', 'install']
    cmd.extend(packages)
    
    try:
        subprocess.run(cmd, check=True)
        print('[EnvKit] Info: Package installation completed')
    except subprocess.CalledProcessError as e:
        print(f'[EnvKit] Warning: Package installation failed ({e})')

# --------------------------------------------------

def detect_platform():
    # Test if it is colab
    try:
        import google.colab
        return 'colab'
    except ImportError:
        pass

    # Test if it is kaggle
    if (
       Path('/kaggle/').exists() and
       Path('/kaggle/input/').exists() and
       Path('/kaggle/working/').exists() and
       Path('/kaggle/temp/').exists()
    ):
       return 'kaggle'
    
    # None of the above, assume it is local
    return 'local'

def get_secrets(platform):
    secrets = {
        'GITHUB_TOKEN': None,
        'KAGGLE_USERNAME': None,
        'KAGGLE_KEY': None
    }
    
    print(f'[EnvKit] Info: Loading secrets for platform {platform}...')

    # colab secrets
    if platform == 'colab':
        try:
            from google.colab import userdata
            try: secrets['GITHUB_TOKEN'] = userdata.get('GITHUB_TOKEN')
            except Exception: pass
            try: secrets['KAGGLE_USERNAME'] = userdata.get('KAGGLE_USERNAME')
            except Exception: pass
            try: secrets['KAGGLE_KEY'] = userdata.get('KAGGLE_KEY')
            except Exception: pass
        except ImportError:
            print('[EnvKit] Warning: Failed to import userdata from google.colab')
            print('[EnvKit] Warning: Skipped colab secrets')

    # kaggle secrets
    elif platform == 'kaggle':
        try:
            from kaggle_secrets import UserSecretsClient
            user_secrets = UserSecretsClient()
            try: secrets['GITHUB_TOKEN'] = user_secrets.get_secret('GITHUB_TOKEN')
            except Exception: pass
            try: secrets['KAGGLE_USERNAME'] = user_secrets.get_secret('KAGGLE_USERNAME')
            except Exception: pass
            try: secrets['KAGGLE_KEY'] = user_secrets.get_secret('KAGGLE_KEY')
            except Exception: pass
        except ImportError:
            print('[EnvKit] Warning: Failed to import UserSecretsClient from kaggle_secrets')
            print('[EnvKit] Warning: Skipped kaggle secrets')

    # local (.env)
    else:
        try:
            load_dotenv()
            secrets['GITHUB_TOKEN'] = os.getenv('GITHUB_TOKEN')
            secrets['KAGGLE_USERNAME'] = os.getenv('KAGGLE_USERNAME')
            secrets['KAGGLE_KEY'] = os.getenv('KAGGLE_KEY')
        except Exception as e:
            print(f'[EnvKit] Warning: Failed to load .env ({e})')
            print('[EnvKit] Warning: Skipped .env')
            pass

    if secrets['GITHUB_TOKEN'] is None:
        print('[EnvKit] Warning: GITHUB_TOKEN not found')
    if secrets['KAGGLE_USERNAME'] is None:
        print('[EnvKit] Warning: KAGGLE_USERNAME not found')
    if secrets['KAGGLE_KEY'] is None:
        print('[EnvKit] Warning: KAGGLE_KEY not found')
    
    return secrets

# --------------------------------------------------

def extract_file(file_path, extract_to=None, remove_archieve=False):
    path = Path(file_path)
    if not path.exists():
        print(f'[EnvKit] Warning: File not found ({file_path})')
        return
    if not path.is_file():
        print(f'[EnvKit] Warning: Not a file ({file_path})')
        return

    target_dir = extract_to if extract_to else path.parent
    
    print(f'[EnvKit] Info: Extracting {path.name} -> {target_dir}')
    
    try:
        if path.suffix == '.zip':
            with zipfile.ZipFile(path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
        elif path.name.endswith(('.tar', '.tar.gz', '.tar.xz', '.tgz')):
            with tarfile.open(path, 'r') as tar_ref:
                tar_ref.extractall(target_dir)
        else:
            print(f'[EnvKit] Warning: Unknown archive format ({file_path})')
            print('[EnvKit] Warning: Skipped extraction')
            return
        print('[EnvKit] Info: Extraction completed.')
        
        if remove_archieve:
            os.remove(path)
            print(f'[EnvKit] Info: Removed source archieve ({path.name})')
            
    except Exception as e:
        print(f'[EnvKit] Warning: Extraction failed ({e})')

def execute_script(script_path):
    path = Path(script_path)
    if not path.exists():
        print(f'[EnvKit] Warning: Script not found ({script_path})')
        return
    if not path.is_file():
        print(f'[EnvKit] Warning: Not a file ({script_path})')
        return

    print(f'[EnvKit] Info: Executing script ({script_path})')
    
    try:
        if path.suffix == '.ipynb':
            print('[EnvKit] Info: Converting notebook to python script...')
            subprocess.run([
                sys.executable, '-m', 'jupyter', 'nbconvert',
                '--to', 'python', str(path)
            ], check=True)

            py_file_path = path.with_suffix('.py')
            if not py_file_path.exists():
                print(f'[EnvKit] Warning: Converted script not found ({py_file_path})')
                return

            print(f'[EnvKit] Info: Running converted script ({py_file_path})')
            subprocess.run([sys.executable, str(py_file_path)], check=True)
            
        elif path.suffix == '.py':
            print(f'[EnvKit] Info: Running script ({path})')
            subprocess.run([sys.executable, str(path)], check=True)
        
        else:
             print(f'[EnvKit] Warning: Skipped execution for non-python file ({path.name})')

        print('[EnvKit] Info: Execution finished successfully.')
        
    except subprocess.CalledProcessError as e:
        print(f'[EnvKit] Warning: Execution failed ({e})')

# --------------------------------------------------

def download_file(url, target_path):
    print(f'[EnvKit] Info: Downloading from URL ({url} -> {target_path})')
    try:
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, target_path)
        print('[EnvKit] Info: Download completed')
    except Exception as e:
        print(f'[EnvKit] Warning: Download failed ({e})')

def download_github(url, target_path, resource_type, token=None):
    print(f'[EnvKit] Info: Processing github {resource_type} ({url} -> {target_path})')

    if resource_type == 'repo':
        final_url = url
        if token and url.startswith("https://"):
            final_url = url.replace("https://", f"https://{token}@")
        
        try:
            if Path(target_path).exists():
                print(f'[EnvKit] Warning: Target path {target_path} already exists')
                print('[EnvKit] Warning: Skipped clone')
                return
            subprocess.run(['git', 'clone', final_url, target_path], check=True)
            print('[EnvKit] Info: Git clone completed')
        except subprocess.CalledProcessError as e:
            print(f'[EnvKit] Warning: Git clone failed ({e})')

    elif resource_type == 'file':
        # If the url contains '/tree/', meaning it is a folder
        if '/tree/' in url:
            print(f'[EnvKit] Warning: URL contains \'/tree/\', which is a folder')
            print('[EnvKit] Warning: \'github_file\' is for single file only')
            return

        # If the url contains '/blob/', meaning it is a file (but a webpage)
        # Then, it is necessary to transfer it to raw url
        if 'github.com' in url and '/blob/' in url:
            raw_url = url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
        else:
            raw_url = url

        try:
            req = urllib.request.Request(raw_url)
            if token:
                req.add_header('Authorization', f'token {token}')
            
            Path(target_path).parent.mkdir(parents=True, exist_ok=True)
            
            with urllib.request.urlopen(req) as response, open(target_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            print('[EnvKit] Info: GitHub file download completed')
        except Exception as e:
            print(f'[EnvKit] Warning: GitHub file download failed ({e})')
            print(f'[EnvKit] Debug: Raw URL is {raw_url}')
            
    else:
        print(f'[EnvKit] Warning: Unknown resource type ({resource_type})')

def download_kaggle(name, target_path, resource_type):
    print(f'[EnvKit] Info: Downloading kaggle {resource_type} ({name} -> {target_path})')

    if resource_type == 'competition_files':
        cmd = ['kaggle', 'competitions', 'download', '-c']
    elif resource_type == 'dataset':
        cmd = ['kaggle', 'datasets', 'download', '-d']
    cmd.extend([name, '-p', target_path])
    
    try:
        subprocess.run(cmd, check=True)
        print('[EnvKit] Info: Kaggle download completed')
    except subprocess.CalledProcessError as e:
        print(f'[EnvKit] Warning: Kaggle download failed ({e})')
        print('[EnvKit] Tip: Check if the competition/dataset name is correct')
        print('[EnvKit] Tip: Check if you accepted the competition rules on Kaggle website')

def process_downloads(config, secrets):
    tasks = config.get('download', [])
    if not tasks:
        print('[EnvKit] Info: No download tasks found')
        return
    if isinstance(tasks, dict):
        tasks = [tasks]

    print(f'[EnvKit] Info: Processing {len(tasks)} download tasks...')

    for task in tasks:
        target_path = task.get('path', '.')
        kaggle_downloaded_archive_path = None
        if 'url' in task:
            download_file(task['url'], target_path)
        elif 'github_file' in task:
            download_github(task['github_file'], target_path, 'file', secrets['GITHUB_TOKEN'])
        elif 'github_repo' in task:
            download_github(task['github_repo'], target_path, 'repo', secrets['GITHUB_TOKEN'])
        elif 'kaggle_competition' in task:
            name = task['kaggle_competition']
            download_kaggle(name, target_path, 'competition_files')
            kaggle_downloaded_archive_path = Path(target_path) / f"{name}.zip"
        elif 'kaggle_dataset' in task:
            name = task['kaggle_dataset']
            download_kaggle(name, target_path, 'dataset')
            dataset_slug = name.split('/')[-1]
            kaggle_downloaded_archive_path = Path(target_path) / f"{dataset_slug}.zip"

        if task.get('extract') is True:
            extract_to = task.get('extract_to')
            remove_archieve = task.get('remove_compression', False)
            if 'kaggle_competition' in task or 'kaggle_dataset' in task:
                target_path = kaggle_downloaded_archive_path
            extract_file(target_path, extract_to, remove_archieve)

        if task.get('execute') is True:
            execute_script(target_path)

# --------------------------------------------------

def setup(yaml_path):
    # Load config file
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f'[EnvKit] Error: Config file not found ({yaml_path})')
        return False
    except yaml.YAMLError as e:
        print(f'[EnvKit] Error: YAML syntax error ({e})')
        return False
    print(f'[EnvKit] Info: Config file is {yaml_path}')
    
    # Get the platform
    platform = config.get('platform', 'auto')
    if platform not in ['auto', 'colab', 'kaggle', 'local']:
        print(f'[EnvKit] Error: Invalid platform ({platform})')
        return
    if platform == 'auto':
        platform = detect_platform()
    print(f'[EnvKit] Info: Platform is {platform}')

    # Load secrets
    secrets = get_secrets(platform)

    # Set kaggle credentials
    if secrets["KAGGLE_USERNAME"] and secrets["KAGGLE_KEY"]:
        os.environ["KAGGLE_USERNAME"] = secrets["KAGGLE_USERNAME"]
        os.environ["KAGGLE_KEY"] = secrets["KAGGLE_KEY"]
        print(f"[EnvKit] Info: Kaggle credentials set for {secrets['KAGGLE_USERNAME']}")
    else:
        print('[EnvKit] Warning: Kaggle credentials not set')

    # Install the packages specified in config file
    install_packages(config)

    # Start to download files
    process_downloads(config, secrets)

    return True;

# --------------------------------------------------

def create_parser():
    # Create parser
    parser = argparse.ArgumentParser(
        description=(
            'commands:\n'
            '    python3 envkit.py setup\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # subparsers container
    subparsers = parser.add_subparsers(dest='command', required=True)

    # setup parser
    setup_parser = subparsers.add_parser('setup')
    setup_parser.add_argument(
        '-p', '--path',
        default='envkit.yaml'
    )

    return parser

def main():
    # Create parser
    parser = create_parser()

    # Parse the arguments
    args = parser.parse_args()

    # Execute the corresponding behaviors
    match args.command:
        case 'setup':
            is_successful = setup(args.path)
        case _:
            print('[EnvKit] Error: Invalid command')
            is_successful = False
    
    sys.exit(0 if is_successful else 1)

if __name__ == '__main__':
    main()
