"use client"

import { motion } from "framer-motion"
import { usePathname } from "next/navigation"
import Link from "next/link"
import { BarChart3, FileText, Settings, Zap } from "lucide-react"
import { cn } from "@/lib/utils"

export function Sidebar() {
  const pathname = usePathname()

  const navItems = [
    { href: "/", label: "Home", icon: Zap },
    { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
    { href: "/new-job", label: "New Job", icon: FileText },
    { href: "/results", label: "Results", icon: BarChart3 },
    { href: "/settings", label: "Settings", icon: Settings },
  ]

  return (
    <motion.aside
      initial={{ x: -256 }}
      animate={{ x: 0 }}
      className="w-64 bg-card border-r border-border min-h-screen sticky top-0"
    >
      <div className="p-6 border-b border-border">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <Zap className="w-5 h-5 text-primary-foreground" />
          </div>
          <h1 className="text-lg font-bold">Sustainability Manager</h1>
        </div>
        <p className="text-xs text-muted-foreground">Document Intelligence</p>
      </div>

      <nav className="p-4 space-y-2">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = pathname === item.href

          return (
            <motion.div key={item.href} whileHover={{ x: 4 }} whileTap={{ scale: 0.98 }}>
              <Link
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-4 py-3 rounded-lg transition-colors",
                  isActive ? "bg-primary/20 text-primary font-medium" : "text-muted-foreground hover:bg-card/50",
                )}
              >
                <Icon className="w-5 h-5" />
                <span>{item.label}</span>
                {isActive && <motion.div layoutId="active-indicator" className="ml-auto w-1 h-6 bg-primary rounded" />}
              </Link>
            </motion.div>
          )
        })}
      </nav>
    </motion.aside>
  )
}
