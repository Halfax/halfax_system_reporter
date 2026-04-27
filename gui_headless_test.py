import time
import traceback

try:
    import main
    # Create the GUI which schedules data gathering via Tk 'after' callbacks
    root = main.create_gui()

    # Run the Tk event loop for a short period to allow scheduled population
    start = time.time()
    timeout = 6.0
    try:
        while time.time() - start < timeout:
            root.update()
            time.sleep(0.05)
    except Exception:
        pass

    # Inspect text widgets
    if hasattr(main, 'text_widgets'):
        for key, widget in main.text_widgets.items():
            try:
                txt = widget.get('1.0', 'end')
                first = txt.splitlines()[0] if txt.splitlines() else '<empty>'
                print(f"TAB '{key}': length={len(txt)} first_line={first}")
            except Exception as e:
                print(f"Error reading widget {key}: {e}")
    else:
        print('main.text_widgets not found')

    try:
        root.destroy()
    except Exception:
        pass
except Exception as e:
    print('Failed to import or run main:', e)
    traceback.print_exc()
