# ANSI Color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

# Status indicators with colors
SUCCESS_EMOJI = f"{GREEN}[PASS]{RESET}"
ERROR_EMOJI = f"{RED}[ERROR]{RESET}"

def print_success(message):
    """Print a success message in green"""
    print(f"{GREEN}{message}{RESET}")

def print_error(message):
    """Print an error message in red"""
    print(f"{RED}{message}{RESET}")

def print_info(message):
    """Print an info message in blue"""
    print(f"{BLUE}{message}{RESET}")

def print_warning(message):
    """Print a warning message in yellow"""
    print(f"{YELLOW}{message}{RESET}") 