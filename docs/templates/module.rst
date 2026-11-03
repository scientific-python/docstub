``{{ fullname }}``
=={{ underline }}==

.. currentmodule:: {{ fullname }}

.. automodule:: {{ fullname }}

{% block functions %}
{% if functions %}
{{ _('Functions') | underline(line='-') }}

.. autosummary::
    :toctree:
    :template: objects.rst
    :nosignatures:

  {% for item in functions if not item.startswith("_") %}
    {{ item -}}
  {% endfor %}
  {% for item in functions if item.startswith("_") %}
    {{ item -}}
  {% endfor %}
  {% endif %}
  {%- endblock %}

{% block classes %}
{% if classes %}
{{ _('Classes') | underline(line='-') }}

.. autosummary::
    :toctree:
    :recursive:
    :template: objects.rst
    :nosignatures:

  {% for item in classes if not item.startswith("_") %}
    {{ item -}}
  {% endfor %}
  {% for item in classes if item.startswith("_") %}
    {{ item -}}
  {% endfor %}
{% endif %}
{%- endblock %}