import subprocess

def run_gemini_command(command):
    try:
        result = subprocess.run(['gemini', *command], check=True, stdout=subprocess.PIPE)
        return result.stdout.decode()
    except subprocess.CalledProcessError as e:
        return f'Error: {e}'