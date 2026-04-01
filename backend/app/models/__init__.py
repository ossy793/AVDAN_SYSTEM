# Import all models so SQLAlchemy metadata is populated before create_all()
from app.models.user import User, UserRole  # noqa: F401
from app.models.vendor import VendorProfile  # noqa: F401
from app.models.rider import RiderProfile  # noqa: F401
from app.models.agent_hub import AgentHub, AgentHubStaff  # noqa: F401
from app.models.product import Product, ProductCategory  # noqa: F401
from app.models.order import Order, OrderItem, OrderStatus  # noqa: F401
from app.models.payment import Payment, Escrow, PaymentStatus  # noqa: F401
from app.models.wallet import Wallet, WalletTransaction, TransactionType  # noqa: F401
from app.models.notification import Notification, Message  # noqa: F401
