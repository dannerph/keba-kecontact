import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="keba_kecontact",
    version="1.1.0",
    author="Philipp Danner",
    author_email="philipp@danner-web.de",
    description="A python library to communicate with the KEBA charging stations via udp",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/dannerph/keba-kecontact",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)