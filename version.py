"""DQS Apps: version and where updates come from.

You don't edit __version__ by hand: the GitHub Action writes the tag you push (v1.3.0 -> "1.3.0")
here before building the .exe. Locally it stays at the value below.
"""
__version__ = "1.0.0"

# GitHub repository that holds the releases: "owner/name"
UPDATE_REPO = "HugoRodMon/QCA"

# Name of the .exe attached to each release (the Action uploads it with this name)
EXE_NAME = "DQSApps.exe"
