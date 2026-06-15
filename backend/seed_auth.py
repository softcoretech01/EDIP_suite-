import os
import sys
import bcrypt
from dotenv import load_dotenv

load_dotenv(override=True)

# Ensure backend root is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.database import SessionLocal, Base, engine
from app.models import models

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def seed():
    print("Connecting to database...")
    db = SessionLocal()
    try:
        # Create all tables first just to make sure
        Base.metadata.create_all(bind=engine)
        print("Ensured tables exist in database.")

        # 1. Seed Permissions
        permissions_data = [
            {"name": "view_dashboard", "description": "View ERP dashboard panels"},
            {"name": "manage_erp", "description": "Add, edit, or delete ERP connections"},
            {"name": "chat_erp", "description": "Interact with the AI chatbot to query ERP data"},
            {"name": "admin_settings", "description": "Manage administrative configuration"},
        ]
        
        permissions = {}
        for p_data in permissions_data:
            existing = db.query(models.Permission).filter(models.Permission.name == p_data["name"]).first()
            if not existing:
                perm = models.Permission(name=p_data["name"])
                db.add(perm)
                db.commit()
                db.refresh(perm)
                print(f"Created permission: {perm.name}")
                permissions[perm.name] = perm
            else:
                permissions[p_data["name"]] = existing
                print(f"Permission already exists: {existing.name}")

        # 2. Seed Roles
        roles_data = {
            "Administrator": {
                "description": "Full access to the entire platform",
                "permissions": ["view_dashboard", "manage_erp", "chat_erp", "admin_settings"]
            },
            "Manager": {
                "description": "Standard business operations manager",
                "permissions": ["view_dashboard", "manage_erp", "chat_erp"]
            },
            "Viewer": {
                "description": "View-only access to dashboards and chatbot",
                "permissions": ["view_dashboard", "chat_erp"]
            }
        }

        roles = {}
        for role_name, info in roles_data.items():
            role = db.query(models.Role).filter(models.Role.name == role_name).first()
            if not role:
                role = models.Role(name=role_name, description=info["description"])
                db.add(role)
                db.commit()
                db.refresh(role)
                print(f"Created role: {role.name}")
            else:
                print(f"Role already exists: {role.name}")
            roles[role_name] = role

            # Sync permissions to role
            for p_name in info["permissions"]:
                perm = permissions[p_name]
                rp = db.query(models.RolePermission).filter(
                    models.RolePermission.role_id == role.id,
                    models.RolePermission.permission_id == perm.id
                ).first()
                if not rp:
                    rp = models.RolePermission(role_id=role.id, permission_id=perm.id)
                    db.add(rp)
                    db.commit()
                    print(f"Mapped permission '{p_name}' to role '{role_name}'")

        # 3. Seed Default Tenant
        tenant = db.query(models.Tenant).filter(models.Tenant.id == 1).first()
        if not tenant:
            tenant = models.Tenant(id=1, name="Tradeware Tenant")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print(f"Created default tenant: {tenant.name}")
        else:
            print(f"Default tenant already exists: {tenant.name}")

        # 4. Seed Users
        users_data = [
            {
                "email": "admin@edip.com",
                "password": "admin123",
                "full_name": "Platform Administrator",
                "role": "Administrator"
            },
            {
                "email": "dev@edip.com",
                "password": "password123",
                "full_name": "Developer User",
                "role": "Manager"
            },
            {
                "email": "viewer@edip.com",
                "password": "viewer123",
                "full_name": "Guest Viewer",
                "role": "Viewer"
            },
            {
                "email": "kabil@gmail.com",
                "password": "kabil123",
                "full_name": "Kabilesh",
                "role": "Administrator"
            }
        ]

        for u_data in users_data:
            user = db.query(models.User).filter(models.User.email == u_data["email"]).first()
            hashed = hash_password(u_data["password"])
            if not user:
                user = models.User(
                    email=u_data["email"],
                    hashed_password=hashed,
                    full_name=u_data["full_name"],
                    tenant_id=tenant.id,
                    is_active=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"Created user: {user.email}")
            else:
                user.hashed_password = hashed
                user.full_name = u_data["full_name"]
                user.tenant_id = tenant.id
                db.commit()
                print(f"Updated password and fields for user: {user.email}")

            # Map user to role
            role = roles[u_data["role"]]
            ur = db.query(models.UserRole).filter(
                models.UserRole.user_id == user.id,
                models.UserRole.role_id == role.id
            ).first()
            if not ur:
                ur = models.UserRole(user_id=user.id, role_id=role.id)
                db.add(ur)
                db.commit()
                print(f"Assigned role '{role.name}' to user '{user.email}'")

        print("Seeding completed successfully!")
    except Exception as e:
        print(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed()
