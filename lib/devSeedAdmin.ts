import { hashPassword } from "@/lib/auth/password";
import { isAdminEmail } from "@/lib/auth/admins";
import {
  createUser,
  findUserByEmail,
  updateUserPasswordHash,
} from "@/lib/repositories/users";

const DEFAULT_DEV_ADMIN_EMAIL = "sunzhangyi415@163.com";
const DEFAULT_DEV_ADMIN_PASSWORD = "dev123456";

export function devAdminCredentials(): {
  email: string;
  password: string;
} {
  return {
    email: (
      process.env.DEV_ADMIN_EMAIL?.trim() || DEFAULT_DEV_ADMIN_EMAIL
    ).toLowerCase(),
    password:
      process.env.DEV_ADMIN_PASSWORD?.trim() || DEFAULT_DEV_ADMIN_PASSWORD,
  };
}

let seeded = false;

export function resetDevAdminSeedFlag(): void {
  seeded = false;
}

/** Ensure a known admin login exists on the file store (dev / first boot). */
export async function ensureDevAdminUser(): Promise<void> {
  if (process.env.NODE_ENV === "production") return;
  if (seeded) return;

  const { email, password } = devAdminCredentials();
  if (!isAdminEmail(email)) return;

  const passwordHash = await hashPassword(password);
  const existing = await findUserByEmail(email);

  if (existing) {
    await updateUserPasswordHash(email, passwordHash);
  } else {
    await createUser({
      email,
      passwordHash,
      displayName: "Admin",
    });
  }

  seeded = true;
}
