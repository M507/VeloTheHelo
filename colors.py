import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
    """Print a success message in green and log as INFO"""
    print(f"{GREEN}{message}{RESET}")
    logger.info(f"SUCCESS: {message}")

def print_error(message):
    """Print an error message in red and log as ERROR"""
    print(f"{RED}{message}{RESET}")
    logger.error(f"ERROR: {message}")

def print_info(message):
    """Print an info message in blue and log as INFO"""
    print(f"{BLUE}{message}{RESET}")
    logger.info(f"INFO: {message}")

def print_warning(message):
    """Print a warning message in yellow and log as WARNING"""
    print(f"{YELLOW}{message}{RESET}")
    logger.warning(f"WARNING: {message}") 