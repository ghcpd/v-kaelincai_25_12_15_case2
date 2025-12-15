import sys
import json
sys.path.insert(0, 'src')
from api_handler import get_ranking_service

service = get_ranking_service()
request = {
    'request_id': 'test-002',
    'students': [
        {'name': 'Alice', 'score': 95},
        {'name': 'Bob', 'score': 95},
        {'name': 'Charlie', 'score': 90}
    ]
}
response, status = service.process_request(request)
print("Full response:")
print(json.dumps(response, indent=2))
