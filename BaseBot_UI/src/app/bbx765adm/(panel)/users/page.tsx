"use client";

import Link from "next/link";
import { AdminDataTable } from "@/components/admin/admin-data-table";
import { ADMIN_HOME, formatEAT } from "@/lib/admin";

type UserRow = {
  id: string;
  email: string;
  role: string;
  plan: string;
  trial_ends_at: string | null;
  last_login_at: string | null;
  suspended_at: string | null;
  created_at: string;
};

export default function AdminUsersPage() {
  return (
    <AdminDataTable<UserRow>
      title="Users"
      path="/users"
      sortKeys={["created_at", "email", "plan", "last_login_at"]}
      columns={[
        {
          key: "email",
          header: "Email",
          render: (user) => (
            <Link href={`${ADMIN_HOME}/users/${user.id}`} className="text-accent-300 hover:underline">
              {user.email}
            </Link>
          ),
        },
        {
          key: "role",
          header: "Role",
          render: (user) => (user.role === "user" ? "user" : user.role),
        },
        { key: "plan", header: "Plan", render: (user) => user.plan },
        {
          key: "trial",
          header: "Trial ends",
          render: (user) => formatEAT(user.trial_ends_at),
        },
        {
          key: "last_login",
          header: "Last login",
          render: (user) => formatEAT(user.last_login_at),
        },
        {
          key: "suspended",
          header: "Status",
          render: (user) =>
            user.suspended_at ? (
              <span className="text-danger-400">Suspended</span>
            ) : (
              <span className="text-secondary">Active</span>
            ),
        },
        {
          key: "created",
          header: "Joined",
          render: (user) => formatEAT(user.created_at),
        },
      ]}
      actions={(user) => (
        <Link
          href={`${ADMIN_HOME}/users/${user.id}`}
          className="text-xs text-accent-300 hover:underline"
        >
          Open
        </Link>
      )}
    />
  );
}
