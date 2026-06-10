"""SQLAlchemy persistence package.

Contains the declarative ``Base``, the ORM table models, and the async
engine / session-factory helpers.  Concrete SQL repositories (BE-2, BE-3) will
build on top of the session factory exposed here.
"""
