.. _installation:

Installation
============

PyWiFeS requires an installation environment with python 3.10, scipy 1.9.1, numpy <2.0, and pip.

To install PyWiFeS, follow these steps:

1. Clone the repository (automation branch):
   
   .. code-block:: bash
   
      git clone -b automation https://github.com/conken/pipeline.git
   
2. Navigate to the project directory and install dependencies:
   
   .. code-block:: bash
   
      pip install .
   
3. Set the `PYWIFES_DIR` environment variable to your reference data directory:
   
   .. code-block:: bash
   
      export PYWIFES_DIR=/.../pipeline/reference_data

4. If desired, set up an alias for the main reduction routine:
   
   .. code-block:: bash
   
      alias pywifes-reduce='/.../pipeline/reduction_scripts/reduce_data.py'
