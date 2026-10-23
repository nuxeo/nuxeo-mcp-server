"""Markdown guides served as ``nuxeo://`` resources.

These live inside the package so that they ship in the wheel and the container
image. Reading them from a path relative to ``__file__`` that escapes the
package worked only in a source checkout.
"""
