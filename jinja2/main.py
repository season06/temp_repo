from jinja2 import Template, StrictUndefined
import json
import yaml

# Load JSON data
# with open('./dev/value.json') as f:
#     value = json.load(f)

# Load YAML data
with open('./dev/value.yaml') as f:
    value = yaml.safe_load(f)

# Jinja2 template
with open('./dev/development_template.j2', 'r') as file:
    template = file.read()

# Render the template
j2_template = Template(template, undefined=StrictUndefined)
rendered_template = j2_template.render(value)

# Save the rendered template to a file
with open('depolyment.yaml', 'w') as f:
    f.write(rendered_template)