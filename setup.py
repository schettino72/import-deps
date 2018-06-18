import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="import_deps",
    version="0.1.0",
    author = 'Eduardo Naufel Schettino',
    author_email = 'schettino72@gmail.com',
    url = 'https://github.com/schettino72/import-deps',
    description='find python module imports',
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    classifiers=(
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Quality Assurance',
    ),
    keywords = "import graph quality",

    python_requires='>=3.5',
    entry_points = {
        'console_scripts': [
            'import_deps = import_deps.__main__:main'
        ]
    },
)
