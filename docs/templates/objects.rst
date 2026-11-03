``{{ name }}``
=={{ underline }}==

in module :mod:`{{ module }}`.

.. currentmodule:: {{ module }}

{% if objtype == "class" -%}
.. autoclass:: {{ fullname }}
  :members:
  :private-members:
  :special-members:
{% else %}
.. auto{{ objtype }}:: {{ fullname }}
{% endif %}
