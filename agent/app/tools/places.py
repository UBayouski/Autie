"""Local-services lookup via Places API (New).

Replaces the old Dialogflow fulfillment path (googlePlacesService.ts), which used
the legacy Text Search endpoint. The agent does the slot-filling that Dialogflow
intents used to: it must know WHAT the user needs and WHERE before calling.

Direct REST by choice: one endpoint, explicit field mask, trivial to mock. If this
grows to more Maps surfaces (Place Details, photos, autocomplete), switch to the
official `google-maps-places` client in one move and use ADC auth instead of the
API key (drops the Secret Manager secret). Do NOT use the legacy `googlemaps`
package - it only supports the old API.
"""

import logging
import os

import httpx

logger = logging.getLogger("autie.places")

_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Only pay for the fields we render. Field mask = billing lever on Places (New).
_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.businessStatus",
    "places.editorialSummary",
])

_MAX_RESULTS = 8


async def find_local_services(what: str, where: str) -> dict:
    """Finds autism-related services and places near a location in the USA.

    Use this when the user wants local, real-world services: therapists (speech,
    occupational, ABA), developmental pediatricians, diagnostic clinics, special
    education schools or programs, support groups, sensory-friendly venues, etc.

    Before calling, make sure you know both what the user is looking for and
    where. If the location is missing or vague (e.g. no city), ask the user
    first instead of guessing.

    Args:
        what: The kind of service or place, e.g. "pediatric occupational therapy"
            or "autism support group". Include the word "autism" when relevant.
        where: City and state (e.g. "Austin, TX"), or a zip code.

    Returns:
        dict with "results": a list of places (name, address, phone, website,
        rating, google_maps_link) ordered by relevance, or "error" on failure.
        Present results factually; do not invent details beyond what's returned.
    """
    api_key = os.getenv("PLACES_API_KEY")
    if not api_key:
        logger.error("PLACES_API_KEY not configured")
        return {"error": "Local services search is not configured."}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                _SEARCH_URL,
                headers={
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": _FIELD_MASK,
                },
                json={
                    "textQuery": f"{what} near {where}",
                    "regionCode": "US",
                    "maxResultCount": _MAX_RESULTS,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("places search failed: HTTP %s", exc.response.status_code)
        return {"error": "The local services search failed. Try again shortly."}
    except httpx.HTTPError as exc:
        logger.error("places search failed: %s", type(exc).__name__)
        return {"error": "The local services search failed. Try again shortly."}

    results = []
    for place in payload.get("places", []):
        if place.get("businessStatus") not in (None, "OPERATIONAL"):
            continue
        results.append({
            "name": place.get("displayName", {}).get("text"),
            "address": place.get("formattedAddress"),
            "phone": place.get("nationalPhoneNumber"),
            "website": place.get("websiteUri"),
            "rating": place.get("rating"),
            "rating_count": place.get("userRatingCount"),
            "summary": place.get("editorialSummary", {}).get("text"),
            "google_maps_link": place.get("googleMapsUri"),
        })

    logger.info("places search ok results=%d", len(results))
    if not results:
        return {
            "results": [],
            "note": "No matching places found. Suggest widening the search area "
                    "or trying a different service type.",
        }
    return {"results": results}
