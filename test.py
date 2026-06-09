import requests

ACCESS_TOKEN = "NLsARBnv0lrR9QfstZVYkXClyAIafF784oMHXTMSvu0.TecoC0Xg5viViCnCHZywYI37JsL2AamqxxiOyo-4ing"  # actualizá si expiró

headers = {
    "Authorization": "Bearer " + ACCESS_TOKEN,
    "Content-Type": "application/json",
}

print("=" * 60)
print("/me  (tu info de Hootsuite)")
print("=" * 60)
resp = requests.get("https://platform.hootsuite.com/v1/me", headers=headers)
print("Status:", resp.status_code)
print(resp.text[:1500])

print("\n" + "=" * 60)
print("/me/organizations  (organizacion y plan)")
print("=" * 60)
resp = requests.get("https://platform.hootsuite.com/v1/me/organizations", headers=headers)
print("Status:", resp.status_code)
print(resp.text[:2000])