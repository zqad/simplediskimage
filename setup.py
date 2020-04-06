from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="simplediskimage",
    version="0.2",
    author="Jonas Eriksson",
    author_email="jonas@upto.se",
    description="Library used to build simple disk images with multiple partitions",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/zqad/simplediskimage/",
    license='Apache-2.0',
    packages=find_packages(),
    install_requires=[
        'pyparted',
    ],
    python_requires='>=3.4',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
)
