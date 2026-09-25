import accessible_output2.outputs.auto

# Initialize once
_screenreader = accessible_output2.outputs.auto.Auto()

def screenreader_speak(text: str, interrupt=True):
    """Send text to the active screen reader (JAWS, NVDA, Narrator, etc)."""
    if text:
        _screenreader.output(text, interrupt)
