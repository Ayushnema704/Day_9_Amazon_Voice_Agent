import logging
import sys
import asyncio
import json
import os
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
    tokenize,
    function_tool,
    RunContext
)
import asyncio
# murf may be provided as a local/custom plugin in some environments.
# Try importing it first and fall back gracefully if it's not installed.
try:
    from livekit.plugins import murf
except Exception:
    murf = None

from livekit.plugins import silero, google, deepgram
try:
    from livekit.plugins import noise_cancellation
except Exception:
    noise_cancellation = None

# Configuration: operation timeouts and optional audio-filter enablement
OP_TIMEOUT = int(os.getenv("AGENT_OP_TIMEOUT", "30"))
# When running against a local LiveKit server, audio filters (LiveKit Cloud)
# may not be available. Allow disabling attempts to enable them via env.
ENABLE_AUDIO_FILTERS = os.getenv("LIVEKIT_ENABLE_AUDIO_FILTERS", "false").lower() in ("1", "true", "yes")
# If audio filters are disabled, ensure the noise_cancellation plugin isn't used
if not ENABLE_AUDIO_FILTERS:
    noise_cancellation = None

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# On Windows the default ProactorEventLoop can interact poorly with some
# file-descriptor based code used by parts of the LiveKit agents watcher
# utilities (duplex_unix). Use the selector event loop policy on Windows to
# avoid OSError/WinError 87 during shutdown and recv_into failures.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        # best-effort; continue if policy can't be set
        pass

# Paths to data files
PRODUCTS_CATALOG_PATH = "amazon_products.json"
ORDERS_LOG_PATH = "amazon_orders.json"

# Global catalog data (loaded once at startup for performance)
CATALOG_DATA = None
# Session-based shopping cart (in-memory for now)
SHOPPING_CART = {}


def load_product_catalog():
    """Load the Amazon product catalog from JSON file."""
    if os.path.exists(PRODUCTS_CATALOG_PATH):
        try:
            with open(PRODUCTS_CATALOG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

                # Normalize and validate product entries to avoid runtime errors
                products = data.get("products", []) if isinstance(data, dict) else []
                normalized = []
                for i, p in enumerate(products):
                    try:
                        if not isinstance(p, dict):
                            logger.warning("Skipping non-dict product entry", extra={"index": i})
                            continue

                        prod = {}
                        prod["id"] = p.get("id") or f"UNKN-{i:04d}"
                        prod["name"] = str(p.get("name") or "Unnamed Product")
                        prod["description"] = str(p.get("description") or "")

                        # Price coercion
                        price = p.get("price", 0)
                        try:
                            prod["price"] = int(price)
                        except Exception:
                            try:
                                prod["price"] = int(float(price))
                            except Exception:
                                prod["price"] = 0
                                logger.debug("Coerced invalid price to 0", extra={"product_id": prod["id"], "raw_price": price})

                        prod["currency"] = p.get("currency") or data.get("store_info", {}).get("currency") or "INR"
                        prod["category"] = str(p.get("category") or "")
                        prod["subcategory"] = str(p.get("subcategory") or "")
                        prod["brand"] = str(p.get("brand") or "")
                        prod["color"] = p.get("color")

                        # In-stock coercion
                        in_stock = p.get("in_stock", False)
                        prod["in_stock"] = bool(in_stock)

                        # Rating coercion
                        rating = p.get("rating", 0)
                        try:
                            prod["rating"] = float(rating)
                        except Exception:
                            prod["rating"] = 0.0

                        prod["attributes"] = p.get("attributes") if isinstance(p.get("attributes"), dict) else {}

                        normalized.append(prod)
                    except Exception:
                        logger.exception("Error normalizing product entry", extra={"index": i, "product": str(p)})
                        continue

                data["products"] = normalized
                return data
        except json.JSONDecodeError:
            logger.warning("Product catalog file is corrupted")
            return {"store_info": {}, "products": []}
    return {"store_info": {}, "products": []}


def load_orders():
    """Load existing order records from JSON file."""
    if os.path.exists(ORDERS_LOG_PATH):
        try:
            with open(ORDERS_LOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("Orders log file is corrupted, starting fresh")
            return []
    return []


def save_orders(orders_data):
    """Save order records to JSON file."""
    try:
        with open(ORDERS_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(orders_data, f, indent=2, ensure_ascii=False)
        logger.info("Order information saved successfully")
    except Exception as e:
        logger.error(f"Error saving order data: {e}")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are an intelligent and friendly Amazon Voice Shopping Assistant. Your name is Alexa Shopping Assistant, and you help customers discover products, answer questions, manage their shopping cart, and complete purchases through natural voice conversations.

**Your Personality:**
- Friendly, helpful, and efficient
- Product-knowledgeable across multiple categories
- Patient and understanding with customer needs
- Professional yet conversational
- Quick to understand context and customer intent
- Focused on providing excellent shopping experience

**Conversation Flow:**
1. **Warm Welcome**: Greet the customer warmly
   - Introduce yourself as their Amazon shopping assistant
   - Ask how you can help them today
   
2. **Discovery & Browsing**: Help customers explore products
   - Listen to what they're looking for (electronics, books, fashion, etc.)
   - Ask clarifying questions about preferences (budget, color, size, brand)
   - Use search_products tool to find relevant items
   - Present 2-3 top options with key details (name, price, rating)
   
3. **Product Information**: Answer detailed questions
   - Provide specifications, features, and benefits
   - Share customer ratings and reviews
   - Explain differences between similar products
   - Always use search_products for accurate information
   
4. **Cart Management**: Help customers build their order
   - Use add_to_cart when customer wants to add items
   - Use view_cart to show current cart contents
   - Use remove_from_cart if they change their mind
   - Keep track of running totals
   
5. **Order Placement**: Complete the purchase smoothly
   - Confirm cart contents before checkout
   - Use create_order to finalize the purchase
   - Provide order confirmation with order ID
   - Explain next steps (delivery, tracking)
   
6. **Order History**: Help customers track their purchases
   - Use get_order_history to show past orders
   - Answer questions about previous purchases
   - Provide order details when requested

**Important Guidelines:**
- Keep responses concise and voice-friendly
- Always use tools to fetch accurate product and order information
- Never make up product details, prices, or availability
- Be proactive about suggesting related items
- Confirm important actions (adding to cart, placing orders)
- Handle multiple items in a single conversation naturally
- Use friendly transitions between browsing and purchasing
- Be transparent about pricing and totals

**Product Categories You Handle:**
- Electronics (headphones, smartwatches, smart home devices)
- Books (all genres and formats)
- Fashion (clothing, footwear, accessories)
- Home & Kitchen (appliances, bedding, decor)
- Sports & Outdoors (equipment, fitness accessories)

**Key Shopping Scenarios:**
- "Show me wireless headphones under 10000"
- "I need a gift for my friend who loves reading"
- "Add the second item to my cart"
- "What's in my cart?"
- "I'll buy everything in my cart"
- "Show me my recent orders"
- "Do you have this in black color?"

**Your Communication Style:**
- "I found some great options for you!"
- "That's a popular choice! It has a 4.7 star rating."
- "I've added it to your cart. Your cart total is now..."
- "Would you like to proceed with checkout?"
- "Your order is confirmed! Order ID is..."

**Critical Rules:**
- ALWAYS use search_products before describing products
- ALWAYS use add_to_cart to add items (never assume)
- ALWAYS confirm before calling create_order
- Keep cart context across the conversation
- Be helpful but respect customer autonomy
- Focus on solving customer needs, not just selling

Remember: You're creating a seamless voice shopping experience. Make it easy, enjoyable, and trustworthy. Every interaction should feel helpful and efficient!""",
        )

    # Internal implementation of the product search logic. Kept as an internal helper
    # so the function-tool exposed to the LLM can accept flexible payload shapes.
    async def _search_products_impl(
        self,
        context: RunContext,
        query: Optional[str] = None,
        category: Optional[str] = None,
        max_price: Optional[int] = None,
        min_price: Optional[int] = None,
        brand: Optional[str] = None,
    ):
        try:
            logger.info(
                f"Searching products for: {query}, category: {category}, max_price: {max_price}, brand: {brand}"
            )

            global CATALOG_DATA
            if CATALOG_DATA is None:
                CATALOG_DATA = load_product_catalog()

            products = CATALOG_DATA.get("products", [])
            logger.debug(f"Product catalog loaded: {len(products)} products")

            query_lower = (query or "").lower()
            matched_products = []

            # Common search terms mapping
            search_aliases = {
                "earphones": ["headphones", "earbuds", "airpods", "earphones", "audio"],
                "headphones": ["headphones", "earbuds", "airpods", "earphones", "audio"],
                "phone": ["phone", "mobile", "smartphone", "iphone", "galaxy"],
                "iphone": ["phone", "mobile", "smartphone", "iphone", "apple"],
                "laptop": ["laptop", "notebook", "computer", "macbook"],
                "watch": ["watch", "smartwatch", "wearable"],
                "shoe": ["shoe", "sneaker", "footwear"],
                "book": ["book", "novel", "reading"],
                "home": ["home", "kitchen", "appliance"],
            }

            # Expand query with aliases
            search_terms = [query_lower] if query_lower else []
            for key, aliases in search_aliases.items():
                if key in query_lower:
                    search_terms.extend(aliases)

            # Filter products based on search criteria
            for product in products:
                try:
                    # process each product inside try to surface bad product data
                    pass
                except Exception:
                    logger.exception("error while inspecting product in search_products", extra={"product": str(product)})
                    continue
                
                # Check query match with expanded search terms
                query_match = False
                if not search_terms:
                    # If no search terms (empty query), don't filter by text
                    query_match = True
                else:
                    for term in search_terms:
                        try:
                            if (
                                term
                                and (
                                    term in product.get("name", "").lower()
                                    or term in product.get("description", "").lower()
                                    or term in product.get("category", "").lower()
                                    or term in product.get("subcategory", "").lower()
                                    or term in product.get("brand", "").lower()
                                )
                            ):
                                query_match = True
                                break
                        except Exception:
                            logger.exception("error matching term against product fields", extra={"term": term, "product": str(product)})
                            continue

                # Apply filters
                category_match = not category or product.get("category", "").lower() == category.lower()
                price_match = True
                if max_price:
                    price_match = price_match and product.get("price", 999999) <= max_price
                if min_price:
                    price_match = price_match and product.get("price", 0) >= min_price
                brand_match = not brand or product.get("brand", "").lower() == brand.lower()

                if query_match and category_match and price_match and brand_match and product.get("in_stock", False):
                    matched_products.append(product)

            logger.debug(
                f"Matched products count: {len(matched_products)} for query '{query}' with terms {search_terms}"
            )

            if not matched_products:
                return (
                    f"I couldn't find any products matching '{query}'. Try browsing our categories: Electronics, Books, Fashion, Home & Kitchen, or Sports & Outdoors."
                )

            # Return top 3 products with essential details
            result = f"I found {len(matched_products)} product(s) for you:\n\n"
            for i, product in enumerate(matched_products[:3], 1):
                result += f"{i}. {product['name']} by {product.get('brand', 'Unknown')}\n"
                result += f"   Price: ₹{product.get('price', 0):,}\n"
                result += f"   Rating: {product.get('rating', 'N/A')}/5 ⭐\n"
                result += f"   {product.get('description', '')[:100]}...\n"
                result += f"   Product ID: {product['id']}\n\n"

            if len(matched_products) > 3:
                result += f"...and {len(matched_products) - 3} more. Let me know if you'd like to see more options!"

            return result
        except Exception:
            logger.exception("error in search_products")
            return "I apologize, but I'm having trouble searching for products right now. Please try again in a moment."

    @function_tool
    async def search_products(
        self,
        context: RunContext,
        payload: Optional[dict] = None,
    ):
        """Flexible wrapper around product search.

        Accepts arbitrary payload shapes produced by different LLM function-calling
        behaviors (e.g., `{"query": "earphones"}`) and normalizes them before
        delegating to the internal implementation.
        """
        try:
            data = payload or {}
            # If a JSON string was passed as payload, try to decode it
            if isinstance(data, str):
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict):
                        data = parsed
                    else:
                        data = {"query": str(data)}
                except Exception:
                    data = {"query": data}

            # Common key aliases
            query = (
                data.get("query")
                or data.get("q")
                or data.get("text")
                or data.get("message")
                or data.get("msg")
            )
            category = data.get("category") or data.get("cat")
            brand = data.get("brand")

            def to_int(v):
                if v is None:
                    return None
                try:
                    return int(v)
                except Exception:
                    try:
                        return int(float(v))
                    except Exception:
                        return None

            max_price = to_int(data.get("max_price") or data.get("maxPrice") or data.get("max"))
            min_price = to_int(data.get("min_price") or data.get("minPrice") or data.get("min"))

            return await self._search_products_impl(
                context=context,
                query=query,
                category=category,
                max_price=max_price,
                min_price=min_price,
                brand=brand,
            )
        except Exception:
            logger.exception("error in search_products (flexible wrapper)")
            return "I couldn't understand that search request. Could you rephrase what you're looking for?"

    @function_tool
    async def add_to_cart(
        self,
        context: RunContext,
        product_id: Optional[Any] = None,
        product_name: Optional[Any] = None,
        quantity: int = 1,
    ):
        """Add a product to the customer's shopping cart.
        
        Call this when customer says:
        - "Add this to my cart"
        - "I'll take the second item"
        - "Add 2 of these"
        
        Args:
            product_id: The product ID (e.g., "AMZN-ELEC-001") from search results
            quantity: Number of items to add (default: 1)
        """
        try:
            logger.info(f"Adding to cart - Product: {product_id or product_name}, Quantity: {quantity}")

            global CATALOG_DATA, SHOPPING_CART
            if CATALOG_DATA is None:
                CATALOG_DATA = load_product_catalog()

            # Find product
            products = CATALOG_DATA.get("products", [])
            product = None
            # Normalize if product_id/product_name were passed as dict-like payloads
            try:
                if isinstance(product_id, dict):
                    product_id = product_id.get("product_id") or product_id.get("id") or product_id.get("productId")
                if isinstance(product_name, dict):
                    product_name = product_name.get("product_name") or product_name.get("product") or product_name.get("name")
            except Exception:
                # normalization best-effort; continue
                pass

            # Try lookup by explicit product_id first
            if product_id:
                product = next((p for p in products if p.get("id") == str(product_id)), None)

            # If product not found and a product_name was provided, try fuzzy/name match
            if not product and product_name:
                try:
                    pname = str(product_name).lower()
                except Exception:
                    pname = None
                product = next(
                    (
                        p
                        for p in products
                        if pname and (pname in p.get("name", "").lower() or pname in p.get("description", "").lower())
                    ),
                    None,
                )

            # If still not found and product_id looks like a full product payload (json), try parsing
            if not product and product_id and isinstance(product_id, str):
                try:
                    parsed = json.loads(product_id)
                    if isinstance(parsed, dict):
                        candidate_id = parsed.get("id")
                        if candidate_id:
                            product = next((p for p in products if p.get("id") == candidate_id), None)
                except Exception:
                    # not a JSON payload, ignore
                    pass

            if not product:
                logger.warning("add_to_cart - product not found", extra={"product_id": product_id, "product_name": product_name})
                return f"Sorry, I couldn't find that product. Please try searching again."

            # Add to cart
            try:
                session_id = context.room.name  # Use room name as session ID
            except Exception:
                session_id = "unknown_session"

            if session_id not in SHOPPING_CART:
                SHOPPING_CART[session_id] = []

            # Use canonical product id from the matched product
            pid = product.get("id")

            # Ensure quantity is an int
            try:
                qty = int(quantity)
            except Exception:
                qty = 1

            logger.debug("add_to_cart diagnostics", extra={"session": session_id, "pid": pid, "incoming_product_id": product_id, "incoming_product_name": product_name})

            # Check if product already in cart (compare by canonical id)
            existing_item = next((item for item in SHOPPING_CART[session_id] if item.get("product_id") == pid), None)
            if existing_item:
                existing_item["quantity"] = existing_item.get("quantity", 0) + qty
            else:
                SHOPPING_CART[session_id].append({
                    "product_id": pid,
                    "name": product.get("name"),
                    "price": product.get("price", 0),
                    "quantity": qty,
                })

            # Calculate cart total
            cart_total = sum(item.get("price", 0) * item.get("quantity", 0) for item in SHOPPING_CART[session_id])

            logger.info("product added to cart", extra={"product_id": product.get("id"), "session": session_id})
            return f"Added {quantity} x {product['name']} to your cart! Cart total: ₹{cart_total:,}. Would you like to continue shopping or proceed to checkout?"
        except Exception:
            logger.exception("error in add_to_cart")
            return "Sorry, I couldn't add that to your cart due to an internal error. Please try again."

    @function_tool
    async def add_to_cart_flexible(
        self,
        context: RunContext,
        payload: Optional[dict] = None,
    ):
        """Flexible wrapper around `add_to_cart` to accept varied payload shapes from LLMs.

        Accepts keys like `product_id`, `product`, `productName`, or a JSON string containing product info.
        """
        try:
            data = payload or {}
            if isinstance(data, str):
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict):
                        data = parsed
                    else:
                        data = {"product_name": str(data)}
                except Exception:
                    data = {"product_name": data}

            product_id = data.get("product_id") or data.get("id") or data.get("productId")
            product_name = data.get("product_name") or data.get("product") or data.get("productName") or data.get("name")
            quantity = data.get("quantity") or data.get("qty") or data.get("count") or 1

            return await self.add_to_cart(context=context, product_id=product_id, product_name=product_name, quantity=int(quantity))
        except Exception:
            logger.exception("error in add_to_cart_flexible")
            return "I couldn't understand the add-to-cart request. Could you confirm the product you'd like to add?"

    @function_tool
    async def view_cart(
        self,
        context: RunContext,
    ):
        """View the current shopping cart contents.
        
        Use when customer asks:
        - "What's in my cart?"
        - "Show me my cart"
        - "How much is my total?"
        """
        try:
            logger.info("Viewing cart")

            # Resolve session id safely: RunContext may not always expose `.room`
            session_id = None
            try:
                session_id = getattr(context, "room").name if getattr(context, "room", None) is not None else None
            except Exception:
                session_id = None

            if not session_id:
                # Try common fallback attributes that may be present
                session_id = getattr(context, "room_name", None) or getattr(context, "session_id", None)

            if not session_id:
                session_id = "unknown_session"

            cart_items = SHOPPING_CART.get(session_id, [])

            if not cart_items:
                return "Your cart is empty. Would you like me to help you find some products?"

            result = f"Your shopping cart ({len(cart_items)} item(s)):\n\n"
            total = 0
            for i, item in enumerate(cart_items, 1):
                item_total = item.get("price", 0) * item.get("quantity", 0)
                result += f"{i}. {item.get('name')}\n"
                result += f"   Quantity: {item.get('quantity')} x ₹{item.get('price', 0):,} = ₹{item_total:,}\n\n"
                total += item_total

            result += f"Cart Total: ₹{total:,}\n\nReady to checkout?"
            return result
        except Exception:
            logger.exception("error in view_cart")
            return "Sorry, I couldn't retrieve your cart due to an internal error. Please try again."

    @function_tool
    async def remove_from_cart(
        self,
        context: RunContext,
        product_id: str,
    ):
        """Remove a product from the shopping cart.
        
        Use when customer says:
        - "Remove this from my cart"
        - "I don't want the headphones anymore"
        
        Args:
            product_id: The product ID to remove
        """
        try:
            logger.info(f"Removing from cart - Product: {product_id}")

            # Resolve session id safely: RunContext may not always expose `.room`
            session_id = None
            try:
                session_id = getattr(context, "room").name if getattr(context, "room", None) is not None else None
            except Exception:
                session_id = None

            if not session_id:
                # Try common fallback attributes that may be present
                session_id = getattr(context, "room_name", None) or getattr(context, "session_id", None)

            if not session_id:
                session_id = "unknown_session"

            cart_items = SHOPPING_CART.get(session_id, [])

            # Find and remove item
            SHOPPING_CART[session_id] = [item for item in cart_items if item.get("product_id") != product_id]

            if len(SHOPPING_CART[session_id]) < len(cart_items):
                return f"Item removed from cart. Your cart now has {len(SHOPPING_CART[session_id])} item(s)."
            else:
                return "I couldn't find that item in your cart."
        except Exception:
            logger.exception("error in remove_from_cart")
            return "Sorry, I couldn't remove that item due to an internal error. Please try again."

    @function_tool
    async def create_order(
        self,
        context: RunContext,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        delivery_address: Optional[str] = None,
    ):
        """Create an order from the current shopping cart.
        
        Call this when customer confirms checkout:
        - "I'll buy everything"
        - "Proceed to checkout"
        - "Place my order"
        
        Args:
            customer_name: Customer's name for order (optional)
            customer_email: Customer's email for order confirmation (optional)
            delivery_address: Delivery address (optional, can be simplified for demo)
        """
        try:
            logger.info(f"Creating order for customer: {customer_name}")

            # Resolve session id safely: RunContext may not always expose `.room`
            session_id = None
            try:
                session_id = getattr(context, "room").name if getattr(context, "room", None) is not None else None
            except Exception:
                session_id = None

            if not session_id:
                # Try common fallback attributes that may be present
                session_id = getattr(context, "room_name", None) or getattr(context, "session_id", None)

            if not session_id:
                session_id = "unknown_session"

            cart_items = SHOPPING_CART.get(session_id, [])

            if not cart_items:
                return "Your cart is empty. Please add items before checking out."

            # Generate order
            order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
            order_total = sum(item.get("price", 0) * item.get("quantity", 0) for item in cart_items)

            order = {
                "order_id": order_id,
                "timestamp": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S"),
                "customer_name": customer_name or "Guest Customer",
                "customer_email": customer_email,
                "delivery_address": delivery_address or "To be confirmed",
                "status": "CONFIRMED",
                "line_items": [
                    {
                        "product_id": item.get("product_id"),
                        "product_name": item.get("name"),
                        "quantity": item.get("quantity"),
                        "unit_price": item.get("price", 0),
                        "line_total": item.get("price", 0) * item.get("quantity", 0),
                    }
                    for item in cart_items
                ],
                "subtotal": order_total,
                "currency": "INR",
                "source": "Amazon Voice Shopping Assistant",
            }

            # Save order
            orders = load_orders()
            orders.append(order)
            save_orders(orders)

            # Clear cart
            SHOPPING_CART[session_id] = []

            result = f"🎉 Order confirmed!\n\n"
            result += f"Order ID: {order_id}\n"
            result += f"Total: ₹{order_total:,}\n"
            result += f"Items: {len(order['line_items'])}\n\n"
            result += "Your order will be delivered soon. Thank you for shopping with Amazon!"

            return result
        except Exception:
            logger.exception("error in create_order")
            return "Sorry, I couldn't place your order due to an internal error. Please try again."

    @function_tool
    async def create_order_flexible(
        self,
        context: RunContext,
        payload: Optional[Any] = None,
    ):
        """Flexible wrapper that accepts free-form details (dict or text) and calls `create_order`.

        Examples accepted:
        - JSON/dict: {"customer_name": "Alice", "customer_email": "a@b.com", "delivery_address": "..."}
        - Free text: "My name is Alice, email a@b.com, address 123 Main St"
        """
        try:
            data = payload or {}
            if isinstance(data, str):
                text = data.strip()
                # attempt to extract email
                email_match = re.search(r"[\w\.-]+@[\w\.-]+", text)
                email = email_match.group(0) if email_match else None

                # attempt to extract name (look for 'name is' or 'I'm' patterns)
                name = None
                m = re.search(r"name\s*(?:is|:)\s*([A-Z][\w\s'-]+)", text, re.IGNORECASE)
                if m:
                    name = m.group(1).strip()
                else:
                    m2 = re.search(r"I(?:'m| am)\s+([A-Z][\w\s'-]+)", text, re.IGNORECASE)
                    if m2:
                        name = m2.group(1).strip()

                # best-effort address: after 'address' keyword or remaining text minus name/email
                address = None
                m3 = re.search(r"address\s*(?:is|:)?\s*(.+)", text, re.IGNORECASE)
                if m3:
                    address = m3.group(1).strip()
                else:
                    # remove name and email from text and treat remainder as address
                    remainder = text
                    if email:
                        remainder = remainder.replace(email, "")
                    if name:
                        remainder = remainder.replace(name, "")
                    # collapse commas and take last chunk as address
                    parts = [p.strip() for p in remainder.split(',') if p.strip()]
                    if parts:
                        address = parts[-1]

                return await self.create_order(
                    context=context,
                    customer_name=name,
                    customer_email=email,
                    delivery_address=address,
                )

            # If payload is a dict-like object
            if isinstance(data, dict):
                name = data.get("customer_name") or data.get("name") or data.get("full_name")
                email = data.get("customer_email") or data.get("email") or data.get("customerEmail")
                address = data.get("delivery_address") or data.get("address") or data.get("shipping_address")
                return await self.create_order(
                    context=context,
                    customer_name=name,
                    customer_email=email,
                    delivery_address=address,
                )

            # Unknown payload shape, try stringifying and parsing
            return await self.create_order(context=context, customer_name=None, customer_email=None, delivery_address=None)
        except Exception:
            logger.exception("error in create_order_flexible")
            return "I couldn't parse your details. Could you say your full name, email, and address in one message?"

    @function_tool
    async def get_order_history(
        self,
        context: RunContext,
        limit: int = 5,
    ):
        """Retrieve customer's order history.
        
        Use when customer asks:
        - "Show me my orders"
        - "What did I buy before?"
        - "My order history"
        
        Args:
            limit: Maximum number of recent orders to show (default: 5)
        """
        try:
            logger.info("Fetching order history")

            orders = load_orders()

            if not orders:
                return "You don't have any previous orders. Start shopping to create your first order!"

            # Show most recent orders
            recent_orders = sorted(orders, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]

            result = f"Your recent orders ({len(recent_orders)} shown):\n\n"
            for order in recent_orders:
                result += f"Order ID: {order.get('order_id')}\n"
                result += f"Date: {order.get('date')}\n"
                result += f"Items: {len(order.get('line_items', []))}\n"
                result += f"Total: ₹{order.get('subtotal', 0):,}\n"
                result += f"Status: {order.get('status')}\n\n"

            return result
        except Exception:
            logger.exception("error in get_order_history")
            return "Sorry, I couldn't fetch your order history due to an internal error. Please try again."


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    # Use `room_name` to avoid overwriting the reserved `room` LogRecord key
    ctx.log_context_fields = {
        "room_name": ctx.room.name,
    }

    # Track background tasks created by this job so we can cancel them
    # during shutdown to avoid the job hanging while waiting for stray tasks.
    _bg_tasks = set()
    _bg_task_names: Dict[asyncio.Task, str] = {}

    def _schedule_task(coro: asyncio.coroutines, name: Optional[str] = None):
        """Create a background task, give it an optional name, and track it for graceful cancellation."""
        try:
            t = asyncio.create_task(coro)
        except Exception:
            # Fallback: if create_task fails, run in the loop directly
            loop = asyncio.get_event_loop()
            t = loop.create_task(coro)

        _bg_tasks.add(t)
        if name:
            _bg_task_names[t] = name

        def _on_done(_t):
            try:
                _bg_tasks.discard(_t)
                _bg_task_names.pop(_t, None)
            except Exception:
                pass

        t.add_done_callback(_on_done)
        # Use safe extra keys (avoid reserved 'name') and the logging helper
        _debug("scheduled background task", extra={"task": str(t), "bg_name": name})
        return t

    async def _cancel_bg_tasks():
        if not _bg_tasks:
            return
        try:
            _info(f"Cancelling {len(_bg_tasks)} background tasks during shutdown")
            # Cancel all tasks
            for t in list(_bg_tasks):
                try:
                    name = _bg_task_names.get(t)
                    _debug("cancelling background task", extra={"task": str(t), "bg_name": name})
                    t.cancel()
                except Exception:
                    _exception("error cancelling background task")

            # Wait briefly for tasks to finish
            done, pending = await asyncio.wait(list(_bg_tasks), timeout=5)
            if pending:
                for p in pending:
                    _warning("Background task did not finish after cancellation", extra={"task": str(p), "bg_name": _bg_task_names.get(p)})

        except Exception:
            _exception("error while cancelling background tasks during shutdown")

    ctx.add_shutdown_callback(_cancel_bg_tasks)

    # Logging helpers to avoid passing `extra` keys that collide with
    # `ctx.log_context_fields` (logging.makeRecord raises KeyError on dupes).
    def _filter_extra(extra: Optional[Dict]) -> Optional[Dict]:
        if not extra:
            return None
        # Protect against keys that would overwrite LogRecord attributes
        RESERVED_LOGRECORD_KEYS = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
        }

        existing = set(ctx.log_context_fields.keys()) if getattr(ctx, "log_context_fields", None) else set()
        # treat reserved LogRecord keys as existing so they get prefixed
        existing = existing.union(RESERVED_LOGRECORD_KEYS)

        out: Dict = {}
        if isinstance(extra, dict):
            for k, v in extra.items():
                if k in existing:
                    out[f"extra_{k}"] = v
                else:
                    out[k] = v
        return out

    def _info(msg: str, extra: Optional[Dict] = None):
        logger.info(msg, extra=_filter_extra(extra))

    def _debug(msg: str, extra: Optional[Dict] = None):
        logger.debug(msg, extra=_filter_extra(extra))

    def _warning(msg: str, extra: Optional[Dict] = None):
        logger.warning(msg, extra=_filter_extra(extra))

    def _exception(msg: str, extra: Optional[Dict] = None):
        logger.exception(msg, extra=_filter_extra(extra))

    # Set up a voice AI pipeline using OpenAI, Cartesia, AssemblyAI, and the LiveKit turn detector

    # Select TTS implementation: prefer Murf if available, otherwise fall back to Google TTS if installed.
    # If neither is available, leave TTS unset (None) so the session can still run in text-only mode.
    try:
        if murf is not None:
            tts_obj = murf.TTS(
                voice="en-US-matthew",
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True,
            )
        else:
            try:
                tts_obj = google.TTS(voice="alloy")
            except Exception:
                tts_obj = None
    except Exception:
        tts_obj = None

    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt=deepgram.STT(model="nova-3"),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm=google.LLM(
                model="gemini-2.5-flash",
            ),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts=tts_obj,
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        # Using VAD-based turn detection for Windows compatibility
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # Metrics collection, to measure pipeline performance
    # For more information, see https://docs.livekit.io/agents/build/metrics/
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    assistant = Assistant()
    await session.start(
        agent=assistant,
        room=ctx.room,
    )
    
    # Join the room and connect to the user
    await ctx.connect()

    # Fallback: wrap `session.say` so we forward any assistant-produced
    # text to the LiveKit room chat immediately after saying it. This helps
    # in cases where conversation_item_added events may not be observed by
    # the client or are produced in a timing that misses the data channel.
    orig_say = session.say

    async def _say_and_forward(text: str, *args, **kwargs):
        # Call the original session.say to produce speech and conversation items
        try:
            result = await asyncio.wait_for(orig_say(text, *args, **kwargs), timeout=OP_TIMEOUT)
        except asyncio.TimeoutError:
            _warning("session.say timed out", extra={"room_name": ctx.room.name, "text_preview": text[:120]})
            # Best-effort: return a placeholder result or None
            result = None
        except Exception:
            logger.exception("error while running session.say wrapper")
            result = None
        try:
            # Attempt best-effort send of the same text into the room chat
                try:
                    info = await asyncio.wait_for(ctx.room.local_participant.send_text(text), timeout=5)
                    _info("assistant text sent via say wrapper", extra={"room_name": ctx.room.name, "stream_info": str(info)})
                except asyncio.TimeoutError:
                    _warning("send_text in say wrapper timed out", extra={"room_name": ctx.room.name})
                except Exception:
                    _exception("error sending assistant text via say wrapper")
        except Exception:
            logger.exception("error sending assistant text via say wrapper")
        return result

    # Replace session.say with our wrapper
    session.say = _say_and_forward
    # Ensure assistant text messages are forwarded to the LiveKit room chat so
    # the frontend's `useChatMessages` hook can receive and render them.
    @session.on("conversation_item_added")
    def _log_conversation_item(ev):
        try:
            item = ev.item
            itype = getattr(item, "type", None)
            role = getattr(item, "role", None)
            text = getattr(item, "text_content", None)
            _info(
                "conversation_item_added",
                extra={
                    "item_type": itype,
                    "role": role,
                    "text_preview": (text[:160] if text else None),
                },
            )
        except Exception:
            logger.exception("error logging conversation item")

    @session.on("conversation_item_added")
    def _forward_assistant_text(ev):
        try:
            item = ev.item
            # Only publish assistant messages (not user transcripts or tools)
            if getattr(item, "type", None) == "message" and getattr(item, "role", None) == "assistant":
                text = getattr(item, "text_content", None)
                if text:
                    _info("forwarding assistant text to room chat", extra={"room_name": ctx.room.name, "text_preview": text[:120]})

                    async def _send_and_log(t: str):
                        try:
                            # send_text returns info about the text stream; await to catch errors
                            try:
                                info = await asyncio.wait_for(ctx.room.local_participant.send_text(t), timeout=5)
                                _info("assistant text sent", extra={"room_name": ctx.room.name, "stream_info": str(info)})
                            except asyncio.TimeoutError:
                                _warning("assistant send_text timed out", extra={"room_name": ctx.room.name})
                            except Exception:
                                _exception("error sending assistant text to room")
                        except Exception:
                            logger.exception("error sending assistant text to room")

                    # Additionally, attempt to send the same text as a reliable data-channel message
                    # Many LiveKit client apps listen to data channels for chat messages. We'll try
                    # multiple possible method names (publish_data, send_data) to be robust across
                    # SDK versions. These are best-effort and failures are non-fatal.
                    async def _send_data_fallback(t: str):
                        lp = ctx.room.local_participant
                        data = t.encode('utf-8')
                        sent = False
                        try:
                            # Try publish_data(signature may vary)
                            fn = getattr(lp, 'publish_data', None)
                            if fn:
                                try:
                                    await asyncio.wait_for(fn(data), timeout=5)
                                    _info('assistant data published via publish_data')
                                    sent = True
                                except asyncio.TimeoutError:
                                    _warning('publish_data timed out')
                                except Exception:
                                    # some implementations may expect kwargs (reliable=True)
                                    try:
                                        await asyncio.wait_for(fn(data, reliable=True), timeout=5)
                                        _info('assistant data published via publish_data(reliable=True)')
                                        sent = True
                                    except asyncio.TimeoutError:
                                        _warning('publish_data(reliable=True) timed out')
                                    except Exception:
                                        _debug('publish_data failed')

                            if not sent:
                                fn2 = getattr(lp, 'send_data', None) or getattr(lp, 'sendData', None)
                                if fn2:
                                    try:
                                        await asyncio.wait_for(fn2(data), timeout=5)
                                        _info('assistant data sent via send_data')
                                        sent = True
                                    except asyncio.TimeoutError:
                                        _warning('send_data timed out')
                                    except Exception:
                                        try:
                                            await asyncio.wait_for(fn2(data, reliable=True), timeout=5)
                                            _info('assistant data sent via send_data(reliable=True)')
                                            sent = True
                                        except asyncio.TimeoutError:
                                            _warning('send_data(reliable=True) timed out')
                                        except Exception:
                                            _debug('send_data failed')

                        except Exception:
                            _exception('error publishing assistant text as data')

                    try:
                        _schedule_task(_send_data_fallback(text), name="assistant_data_fallback")
                    except Exception:
                        logger.exception('failed to schedule data fallback send')

                    # schedule async publish to avoid blocking the event callback
                    _schedule_task(_send_and_log(text), name="assistant_send_and_log")
        except Exception:
            logger.exception("failed to forward assistant message to room chat")
    
    # Send initial greeting when user connects
    await session.say("Hello! Welcome to Amazon Voice Shopping! I'm your personal shopping assistant, ready to help you discover amazing products across electronics, books, fashion, home goods, and more. What are you looking for today?", allow_interruptions=True)

    # Server-side listener: accept typed chat coming in on the room data channel
    # Many frontends publish typed chat as reliable data with topic `lk.chat` or
    # legacy `lk-chat-topic`. Listen for `data_received` events and inject the
    # decoded text into the AgentSession so typed messages are treated like
    # user transcripts and trigger LLM replies.
    def _decode_data_payload(data: bytes) -> str:
        try:
            text = data.decode("utf-8")
        except Exception:
            try:
                # best-effort fallback
                text = data.decode("latin-1")
            except Exception:
                text = ""

        # try parsing JSON payloads commonly sent by some clients
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return (
                    parsed.get("text")
                    or parsed.get("message")
                    or parsed.get("msg")
                    or text
                )
        except Exception:
            pass

        return text

    def _on_room_data(packet):
        try:
            # packet is a livekit.rtc.DataPacket
            topic = getattr(packet, "topic", None)
            if topic not in ("lk.chat", "lk-chat-topic"):
                return

            # ignore data sent by the local participant (server)
            sender = getattr(packet, "participant", None)
            try:
                local_id = ctx.room.local_participant.identity
            except Exception:
                local_id = None

            if sender is not None and getattr(sender, "identity", None) == local_id:
                return

            payload = getattr(packet, "data", b"") or b""
            text = _decode_data_payload(payload)
            if not text or not text.strip():
                return

            async def _inject_text():
                try:
                    # Mirror the default room text input callback behaviour:
                    # interrupt any current agent speech and generate a reply
                    try:
                        await session.interrupt()
                    except Exception:
                        # non-fatal if interruption fails
                        logger.exception("error interrupting session before injecting text")

                    # Use a timeout to avoid a stuck LLM/generation blocking shutdown
                    try:
                        await asyncio.wait_for(session.generate_reply(user_input=text), timeout=OP_TIMEOUT)
                    except asyncio.TimeoutError:
                        _warning("session.generate_reply timed out for injected text", extra={"room_name": ctx.room.name, "text_preview": text[:160]})
                    except Exception:
                        _exception("error generating reply for injected typed chat")
                    else:
                        # Log successful injection (or timeout was already logged)
                        _info(
                            "Injected typed chat into AgentSession",
                            extra={"room_name": ctx.room.name, "text_preview": text[:160]},
                        )
                except Exception:
                    logger.exception("error injecting typed chat into session")

            try:
                _schedule_task(_inject_text(), name="inject_typed_chat")
            except Exception:
                logger.exception("failed to schedule inject_text task")
        except Exception:
            logger.exception("error handling room data packet")

    try:
        ctx.room.on("data_received", _on_room_data)
    except Exception:
        logger.exception("failed to register room data_received listener")

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))




