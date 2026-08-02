"""HTTP service for GazeFix.

Requires the optional server extras::

    pip install 'gazefix[server]'
"""

from .jobs import Job, JobStatus, JobStore

__all__ = ["Job", "JobStatus", "JobStore"]
