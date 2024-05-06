from setuptools import setup, find_packages

setup(
    name="mydeck",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "pyyaml",
        "streamdeck",
        "qrcode",
    ],
    package_data = {
      "": [".png", ".js", ".html", ".css"],
      "mydeck": ["Assets/*", "html/*", "html/*/*"],
    },
    entry_points={
        "console_scripts": [
            "mydeck = mydeck.my_decks_starter:main",
        ],
    },
)
