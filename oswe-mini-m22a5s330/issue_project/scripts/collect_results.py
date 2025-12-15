import xml.etree.ElementTree as ET
import json
import sys
xml_path = 'issue_project/results/results_post.xml'
json_path = 'issue_project/results/results_post.json'
try:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    suite = root.find('testsuite')
    if suite is None:
        suite = root
    tests = int(suite.attrib.get('tests', 0))
    failures = int(suite.attrib.get('failures', 0))
    errors = int(suite.attrib.get('errors', 0))
    time = float(suite.attrib.get('time', 0.0))
    data = {'tests': tests, 'failures': failures, 'errors': errors, 'time_seconds': time}
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
    print('Wrote', json_path)
except Exception as ex:
    print('Failed to create results JSON:', ex)
    sys.exit(1)
