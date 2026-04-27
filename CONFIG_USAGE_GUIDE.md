# Configuration Usage Guide

This guide explains how to use the centralized configuration system in `config.py` to customize the Halfax System Reporter application.

## Quick Start

```python
# Import the configuration
from config import CONFIG, COLORS, FONTS, LAYOUT, TIMING

# Use colors
root.configure(bg=COLORS.PRIMARY_BACKGROUND)

# Use fonts
title_label = tk.Label(text="Title", font=FONTS.UI_TITLE)

# Use layout
root.geometry(f"{LAYOUT.MAIN_WINDOW_WIDTH}x{LAYOUT.MAIN_WINDOW_HEIGHT}")

# Use timing
root.after(TIMING.SPLASH_INITIAL_DELAY, start_data_collection)
```

## Configuration Categories

### 1. COLORS
All color definitions for the application UI.

```python
# Background colors
COLORS.PRIMARY_BACKGROUND      # '#1a1a1a' - Main window
COLORS.SECONDARY_BACKGROUND    # '#1e1e1e' - Splash screen
COLORS.TERTIARY_BACKGROUND     # '#2d2d2d' - Text widgets

# Text colors
COLORS.PRIMARY_TEXT            # '#d4d4d4' - Main text
COLORS.SECONDARY_TEXT          # '#808080' - Muted text
COLORS.ACCENT_TEXT             # '#007acc' - Accent/titles
COLORS.WHITE_TEXT              # '#ffffff' - Selected elements

# UI elements
COLORS.TAB_SELECTED            # '#0078d4' - Active tab
COLORS.BUTTON_PRIMARY          # '#0078d4' - Primary button
COLORS.PROGRESS_BAR            # '#0078d4' - Progress bar

# Status colors
COLORS.SUCCESS_COLOR           # '#4ec9b0' - Success
COLORS.WARNING_COLOR           # '#ce9178' - Warning
COLORS.ERROR_COLOR             # '#f44747' - Error
```

### 2. FONTS
Typography settings for different UI elements.

```python
# UI fonts
FONTS.UI_TITLE          # ('Segoe UI', 24, 'bold')
FONTS.UI_HEADING        # ('Segoe UI', 14)
FONTS.UI_LABEL          # ('Segoe UI', 11)
FONTS.UI_SMALL          # ('Segoe UI', 10, 'bold')

# Content fonts
FONTS.CONTENT_PRIMARY   # ('Consolas', 10)
FONTS.CONTENT_LARGE     # ('Consolas', 12)
FONTS.CONTENT_SMALL     # ('Consolas', 9)
```

### 3. LAYOUT
Sizing, spacing, and layout parameters.

```python
# Window dimensions
LAYOUT.MAIN_WINDOW_WIDTH   # 900
LAYOUT.MAIN_WINDOW_HEIGHT  # 700
LAYOUT.SPLASH_WIDTH        # 700
LAYOUT.SPLASH_HEIGHT       # 380

# Padding
LAYOUT.WIDGET_PADDING_X    # 10
LAYOUT.WIDGET_PADDING_Y    # 10
LAYOUT.SECTION_PADDING_Y   # 15
LAYOUT.LARGE_PADDING_Y     # 30

# Tables
LAYOUT.TABLE_HEIGHT_SMALL  # 6
LAYOUT.TABLE_HEIGHT_MEDIUM # 8
LAYOUT.TABLE_COLUMN_WIDTH_NARROW   # 80
LAYOUT.TABLE_COLUMN_WIDTH_MEDIUM  # 90
LAYOUT.TABLE_COLUMN_WIDTH_WIDE     # 120
```

### 4. TIMING
Animation and delay settings.

```python
# Splash screen
TIMING.SPLASH_INITIAL_DELAY      # 100ms
TIMING.SPLASH_READY_DELAY        # 500ms
TIMING.SPLASH_PROGRESS_INTERVAL  # 5ms

# Data collection
TIMING.DATA_COLLECTION_STEP_DELAY  # 50ms

# UI refresh
TIMING.AUTO_REFRESH_INTERVAL       # 5000ms
TIMING.DEBOUNCE_DELAY              # 300ms
```

### 5. BEHAVIOR
Feature toggles and application behavior.

```python
# Splash screen
BEHAVIOR.SHOW_SPLASH_SCREEN           # True
BEHAVIOR.SMOOTH_PROGRESS_ANIMATION     # True
BEHAVIOR.STEP_BY_STEP_LOADING          # True

# Data collection
BEHAVIOR.ENABLE_AUTO_REFRESH           # False
BEHAVIOR.COLLECT_ALL_DATA_ON_START     # True

# UI behavior
BEHAVIOR.SHOW_TABLE_HEADERS           # True
BEHAVIOR.ENABLE_ALTERNATING_ROW_COLORS # False
BEHAVIOR.WRAP_TEXT_WIDGETS             # True

# Error handling
BEHAVIOR.SHOW_DETAILED_ERRORS          # False
BEHAVIOR.FALLBACK_ON_ERRORS            # True
```

### 6. CONTENT
Content display and formatting options.

```python
# Number formatting
CONTENT.DECIMAL_PLACES          # 2
CONTENT.SHOW_UNITS             # True
CONTENT.USE_BINARY_PREFIXES    # True

# Temperature
CONTENT.TEMPERATURE_UNIT       # 'C'
CONTENT.SHOW_TEMPERATURE_PROVENANCE  # True

# Storage
CONTENT.STORAGE_UNIT           # 'GB'
CONTENT.SHOW_FREE_SPACE_PERCENTAGE   # True

# Memory
CONTENT.SHOW_MEMORY_PERCENTAGE        # True
CONTENT.SHOW_DETAILED_MEMORY_INFO      # True
```

## Implementation Examples

### Example 1: Creating a Styled Label
```python
from config import COLORS, FONTS

# Instead of:
# title_label = tk.Label(text="Title", font=('Segoe UI', 24, 'bold'), bg='#1e1e1e', fg='#007acc')

# Use:
title_label = tk.Label(
    text="Title",
    font=FONTS.UI_TITLE,
    bg=COLORS.SECONDARY_BACKGROUND,
    fg=COLORS.ACCENT_TEXT
)
```

### Example 2: Creating a Text Widget
```python
from config import COLORS, FONTS, LAYOUT

# Instead of:
# text_widget = scrolledtext.ScrolledText(bg='#2d2d2d', fg='#d4d4d4', font=('Consolas', 10))
# text_widget.pack(fill='both', expand=True, padx=10, pady=10)

# Use:
text_widget = scrolledtext.ScrolledText(
    bg=COLORS.TERTIARY_BACKGROUND,
    fg=COLORS.PRIMARY_TEXT,
    font=FONTS.CONTENT_PRIMARY
)
text_widget.pack(fill='both', expand=True, padx=LAYOUT.WIDGET_PADDING_X, pady=LAYOUT.WIDGET_PADDING_Y)
```

### Example 3: Setting Up Splash Screen Timing
```python
from config import TIMING

# Instead of:
# root.after(100, start_data_collection)
# progress_bar.start(10)

# Use:
root.after(TIMING.SPLASH_INITIAL_DELAY, start_data_collection)
progress_bar.start(TIMING.SPLASH_PROGRESS_INTERVAL)
```

### Example 4: Conditional Behavior Based on Config
```python
from config import BEHAVIOR

# Show splash screen only if enabled
if BEHAVIOR.SHOW_SPLASH_SCREEN:
    create_splash_screen()

# Use step-by-step loading if enabled
if BEHAVIOR.STEP_BY_STEP_LOADING:
    load_data_in_steps()
else:
    load_all_data_at_once()
```

### Example 5: Dynamic Configuration Updates
```python
from config import CONFIG

# Update a setting at runtime
CONFIG.update_setting('behavior', 'ENABLE_AUTO_REFRESH', True)

# Check current setting
if CONFIG.behavior.ENABLE_AUTO_REFRESH:
    start_auto_refresh()
```

## Migration Guide

To migrate existing hardcoded values:

1. **Find hardcoded values** in your code:
   ```python
   # Look for patterns like:
   bg='#1a1a1a'
   font=('Segoe UI', 24, 'bold')
   padx=10, pady=10
   root.after(100, ...)
   ```

2. **Replace with config values**:
   ```python
   # Replace:
   bg='#1a1a1a'
   # With:
   bg=COLORS.PRIMARY_BACKGROUND
   
   # Replace:
   font=('Segoe UI', 24, 'bold')
   # With:
   font=FONTS.UI_TITLE
   
   # Replace:
   padx=10, pady=10
   # With:
   padx=LAYOUT.WIDGET_PADDING_X, pady=LAYOUT.WIDGET_PADDING_Y
   ```

3. **Test the changes** to ensure visual consistency is maintained.

## Benefits of Using Config

1. **Consistency**: All UI elements use the same styling
2. **Maintainability**: Changes in one place update the entire application
3. **Customization**: Easy to create themes or individual tweaks
4. **Documentation**: Clear explanations of what each setting does
5. **Validation**: Built-in validation for reasonable values
6. **Flexibility**: Easy to add new settings or modify existing ones

## Future Enhancements

The config system is designed to be extensible. Future enhancements could include:

1. **Theme switching**: Allow users to select different themes
2. **User preferences**: Save user customizations
3. **Dynamic theming**: Change themes without restarting
4. **Accessibility options**: High contrast, large text modes
5. **Performance profiles**: Different settings for different hardware capabilities

## Best Practices

1. **Always import from config** rather than using hardcoded values
2. **Use descriptive names** when adding new configuration options
3. **Document new settings** with clear explanations
4. **Test with different configurations** to ensure flexibility
5. **Keep related settings grouped** in the appropriate class
6. **Use validation** for settings that have reasonable value ranges
