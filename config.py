"""
Halfax System Reporter - Configuration Settings

This file contains all shared configuration settings, UI themes, and tunable parameters
for the Halfax System Reporter application. Centralizing these settings makes it easier
to maintain consistent styling and allows for easy customization.

Usage:
    from config import UI_CONFIG, COLORS, FONTS, TIMING
    # Use the configuration constants in your code
"""

# =============================================================================
# COLOR SCHEME CONFIGURATION
# =============================================================================
# All colors are defined in hex format for consistency
# These colors are used throughout the application for theming

class COLORS:
    """Color scheme constants used throughout the application"""
    
    # Primary color scheme - Dark theme
    PRIMARY_BACKGROUND = '#1a1a1a'          # Main window background
    SECONDARY_BACKGROUND = '#1e1e1e'        # Splash screen background
    TERTIARY_BACKGROUND = '#2d2d2d'         # Text widget backgrounds
    
    # Text colors
    PRIMARY_TEXT = '#d4d4d4'                 # Main text color
    SECONDARY_TEXT = '#808080'               # Secondary/muted text
    ACCENT_TEXT = '#007acc'                  # Accent color for titles/links
    WHITE_TEXT = '#ffffff'                   # Pure white for selected elements
    
    # UI element colors
    TAB_UNSELECTED = '#222222'               # Unselected tab background
    TAB_SELECTED = '#0078d4'                 # Selected tab background (bright blue)
    TAB_BORDER = '#a0a0a0'                   # Tab border color
    
    # Progress bar colors
    PROGRESS_BAR = '#0078d4'                  # Progress bar fill color
    PROGRESS_BAR_TROUGH = '#333333'          # Progress bar background/track
    
    # Interactive elements
    BUTTON_PRIMARY = '#0078d4'                # Primary button background
    BUTTON_HOVER = '#106ebe'                 # Button hover state
    BUTTON_PRESSED = '#005a9e'               # Button pressed state
    
    # Table and data display
    TABLE_HEADER_BG = '#404040'              # Table header background
    TABLE_ROW_ALT = '#252525'                # Alternating row color
    TABLE_BORDER = '#555555'                  # Table border color
    
    # Status and indicators
    SUCCESS_COLOR = '#4ec9b0'                # Success/operational status
    WARNING_COLOR = '#ce9178'                # Warning/caution status
    ERROR_COLOR = '#f44747'                  # Error/not available status
    INFO_COLOR = '#569cd6'                   # Information color


# =============================================================================
# FONT CONFIGURATION
# =============================================================================
# Font definitions for consistent typography throughout the application

class FONTS:
    """Font configuration for different UI elements"""
    
    # UI fonts - Segoe UI for modern Windows look
    UI_TITLE = ('Segoe UI', 24, 'bold')      # Main title (splash screen)
    UI_HEADING = ('Segoe UI', 14)            # Section headings
    UI_LABEL = ('Segoe UI', 11)               # Standard labels
    UI_SMALL = ('Segoe UI', 10, 'bold')       # Small bold labels (data display)
    
    # Content fonts - Consolas for monospace data display
    CONTENT_PRIMARY = ('Consolas', 10)        # Main content text
    CONTENT_LARGE = ('Consolas', 12)         # Larger content for emphasis
    CONTENT_SMALL = ('Consolas', 9)           # Small content for dense data
    
    # Alternative font options (commented out for future use)
    # UI_TITLE = ('Arial', 24, 'bold')
    # UI_HEADING = ('Helvetica', 14)
    # CONTENT_PRIMARY = ('Courier New', 10)


# =============================================================================
# UI LAYOUT CONFIGURATION
# =============================================================================
# Spacing, sizing, and layout parameters

class LAYOUT:
    """Layout and spacing configuration"""
    
    # Window dimensions
    MAIN_WINDOW_WIDTH = 900
    MAIN_WINDOW_HEIGHT = 700
    SPLASH_WIDTH = 700
    SPLASH_HEIGHT = 380
    
    # Padding and margins
    WIDGET_PADDING_X = 10                    # Horizontal padding for widgets
    WIDGET_PADDING_Y = 10                    # Vertical padding for widgets
    SECTION_PADDING_Y = 15                    # Padding between sections
    LARGE_PADDING_Y = 30                     # Large padding for major elements
    
    # Button and control sizing
    BUTTON_PADDING_X = 12
    BUTTON_PADDING_Y = 6
    
    # Table configuration
    TABLE_HEIGHT_SMALL = 6                   # Small tables (GPU summary)
    TABLE_HEIGHT_MEDIUM = 8                  # Medium tables (temperature/C-state)
    TABLE_COLUMN_WIDTH_NARROW = 80           # Narrow columns
    TABLE_COLUMN_WIDTH_MEDIUM = 90           # Medium columns
    TABLE_COLUMN_WIDTH_WIDE = 120            # Wide columns
    TABLE_COLUMN_WIDTH_EXTRA_WIDE = 180      # Extra wide columns (provenance)
    
    # Progress bar
    PROGRESS_BAR_PADDING_X = 50
    PROGRESS_BAR_PADDING_Y = 20


# =============================================================================
# TIMING CONFIGURATION
# =============================================================================
# Timing parameters for animations, delays, and refresh intervals

class TIMING:
    """Timing configuration for animations and delays"""
    
    # Splash screen timing
    SPLASH_INITIAL_DELAY = 100               # Delay before starting data collection (ms)
    SPLASH_READY_DELAY = 500                 # Delay to show "Ready" status (ms)
    SPLASH_PROGRESS_INTERVAL = 5             # Progress bar animation interval (ms)
    
    # Data collection timing
    DATA_COLLECTION_STEP_DELAY = 50          # Delay between data collection steps (ms)
    
    # UI refresh timing
    AUTO_REFRESH_INTERVAL = 5000             # Auto-refresh interval (ms) - not currently used
    DEBOUNCE_DELAY = 300                     # Delay for debouncing rapid actions (ms)
    
    # Animation timing
    FADE_DURATION = 200                       # Fade animation duration (ms) - for future use
    SLIDE_DURATION = 300                     # Slide animation duration (ms) - for future use


# =============================================================================
# BEHAVIOR CONFIGURATION
# =============================================================================
# Application behavior and feature toggles

class BEHAVIOR:
    """Behavior configuration and feature toggles"""
    
    # Splash screen behavior
    SHOW_SPLASH_SCREEN = True                # Enable/disable splash screen
    SMOOTH_PROGRESS_ANIMATION = True         # Enable smooth progress bar animation
    STEP_BY_STEP_LOADING = True              # Load data in steps for responsive UI
    
    # Data collection behavior
    ENABLE_AUTO_REFRESH = False              # Auto-refresh data periodically
    COLLECT_ALL_DATA_ON_START = True         # Collect all data on application start
    
    # UI behavior
    SHOW_TABLE_HEADERS = True                # Show table headers
    ENABLE_ALTERNATING_ROW_COLORS = False    # Enable alternating row colors in tables
    WRAP_TEXT_WIDGETS = True                 # Enable text wrapping in text widgets
    
    # Error handling
    SHOW_DETAILED_ERRORS = False             # Show detailed error messages to users
    FALLBACK_ON_ERRORS = True                 # Use fallback methods on errors
    
    # Performance
    LAZY_LOAD_TABS = False                   # Load tab content only when accessed
    CACHE_DATA_COLLECTION = True              # Cache data collection results


# =============================================================================
# CONTENT CONFIGURATION
# =============================================================================
# Content display and formatting options

class CONTENT:
    """Content display and formatting configuration"""
    
    # Number formatting
    DECIMAL_PLACES = 2                       # Default decimal places for numbers
    SHOW_UNITS = True                        # Show units (GB, MHz, etc.)
    USE_BINARY_PREFIXES = True               # Use GiB/MiB instead of GB/MB
    
    # Temperature display
    TEMPERATURE_UNIT = 'C'                   # Temperature unit: 'C' or 'F'
    SHOW_TEMPERATURE_PROVENANCE = True       # Show data source for temperatures
    
    # Storage display
    STORAGE_UNIT = 'GB'                       # Default storage unit: 'GB' or 'TB'
    SHOW_FREE_SPACE_PERCENTAGE = True        # Show free space as percentage
    
    # Memory display
    SHOW_MEMORY_PERCENTAGE = True            # Show memory usage as percentage
    SHOW_DETAILED_MEMORY_INFO = True         # Show detailed memory information
    
    # Network display
    SHOW_NETWORK_ERROR_RATES = True          # Show network error rates
    NETWORK_DATA_UNIT = 'MB'                 # Network data unit: 'KB', 'MB', or 'GB'


# =============================================================================
# ADVANCED CONFIGURATION
# =============================================================================
# Advanced settings for power users and developers

class ADVANCED:
    """Advanced configuration options"""
    
    # Debug options
    DEBUG_MODE = False                       # Enable debug mode
    VERBOSE_LOGGING = False                  # Enable verbose logging
    SHOW_PERFORMANCE_METRICS = False        # Show performance metrics
    
    # Development options
    DEVELOPER_MODE = False                   # Enable developer features
    SHOW_WIDGET_IDS = False                  # Show widget IDs for debugging
    ENABLE_HOT_RELOAD = False                # Enable hot reload for development
    
    # Performance tuning
    MAX_WORKER_THREADS = 4                   # Maximum worker threads for parallel tasks
    DATA_COLLECTION_TIMEOUT = 30             # Timeout for data collection (seconds)
    UI_THREAD_BLOCKING_TIMEOUT = 5           # Timeout for UI thread operations (seconds)
    
    # Memory management
    MAX_CACHE_SIZE = 100                     # Maximum cache size (items)
    CACHE_EXPIRY_TIME = 300                  # Cache expiry time (seconds)
    ENABLE_MEMORY_OPTIMIZATION = True       # Enable memory optimization features


# =============================================================================
# THEMES
# =============================================================================
# Predefined theme combinations for easy switching

class THEMES:
    """Predefined theme combinations"""
    
    @staticmethod
    def get_dark_theme():
        """Get the current dark theme configuration"""
        return {
            'colors': COLORS,
            'fonts': FONTS,
            'layout': LAYOUT,
            'timing': TIMING
        }
    
    @staticmethod
    def get_light_theme():
        """Get a light theme configuration (not implemented)"""
        # Future: Define light theme colors
        pass
    
    @staticmethod
    def get_high_contrast_theme():
        """Get a high contrast theme configuration (not implemented)"""
        # Future: Define high contrast theme colors
        pass


# =============================================================================
# VALIDATION CONFIGURATION
# =============================================================================
# Data validation and sanity checks

class VALIDATION:
    """Data validation configuration"""
    
    # Temperature validation
    MIN_REASONABLE_TEMP = -20                # Minimum reasonable temperature (°C)
    MAX_REASONABLE_TEMP = 150                # Maximum reasonable temperature (°C)
    
    # Memory validation
    MIN_REASONABLE_MEMORY_GB = 0.1           # Minimum reasonable memory (GB)
    MAX_REASONABLE_MEMORY_GB = 1024          # Maximum reasonable memory (GB)
    
    # Storage validation
    MIN_REASONABLE_STORAGE_GB = 1            # Minimum reasonable storage (GB)
    MAX_REASONABLE_STORAGE_TB = 100          # Maximum reasonable storage (TB)
    
    # Network validation
    MIN_REASONABLE_NETWORK_SPEED = 0         # Minimum reasonable network speed
    MAX_REASONABLE_NETWORK_SPEED = 100000    # Maximum reasonable network speed (Gbps)


# =============================================================================
# MAIN CONFIGURATION OBJECT
# =============================================================================
# Main configuration object that combines all settings

class UI_CONFIG:
    """Main configuration object containing all UI settings"""
    
    def __init__(self):
        # Load all configuration modules
        self.colors = COLORS
        self.fonts = FONTS
        self.layout = LAYOUT
        self.timing = TIMING
        self.behavior = BEHAVIOR
        self.content = CONTENT
        self.advanced = ADVANCED
        self.validation = VALIDATION
    
    def get_theme(self, theme_name='dark'):
        """Get a specific theme configuration"""
        if theme_name == 'dark':
            return THEMES.get_dark_theme()
        elif theme_name == 'light':
            return THEMES.get_light_theme()
        elif theme_name == 'high_contrast':
            return THEMES.get_high_contrast_theme()
        else:
            return THEMES.get_dark_theme()
    
    def update_setting(self, category, setting, value):
        """Update a configuration setting dynamically"""
        if hasattr(self, category):
            category_obj = getattr(self, category)
            if hasattr(category_obj, setting):
                setattr(category_obj, setting, value)
            else:
                raise ValueError(f"Setting '{setting}' not found in category '{category}'")
        else:
            raise ValueError(f"Category '{category}' not found")


# Create global configuration instance
CONFIG = UI_CONFIG()

# Export commonly used items for convenience
__all__ = [
    'CONFIG', 'COLORS', 'FONTS', 'LAYOUT', 'TIMING', 
    'BEHAVIOR', 'CONTENT', 'ADVANCED', 'VALIDATION', 'THEMES'
]
