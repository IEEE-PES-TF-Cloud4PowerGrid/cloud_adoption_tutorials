"""
Setup configuration for the AMI 2.0 streaming pipeline.

This setup.py is required for Dataflow to properly package and
distribute the pipeline code to worker nodes.
"""

from setuptools import setup, find_packages

setup(
    name='ami_streaming_pipeline',
    version='1.0.0',
    description='AMI 2.0 Smart Meter Streaming Pipeline',
    author='IEEE PES TF Cloud4PowerGrid',
    packages=find_packages(),
    py_modules=['transforms'],  # Include the transforms module
    install_requires=[
        'apache-beam[gcp]>=2.50.0',
        'google-cloud-pubsub>=2.18.0',
        'google-cloud-bigquery>=3.11.0',
        'google-cloud-storage>=2.10.0',
        'python-dateutil>=2.8.2',
    ],
    python_requires='>=3.9',
)
