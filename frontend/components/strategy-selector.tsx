"use client"

import { motion } from "framer-motion"
import { Card } from "@/components/ui/card"
import { Leaf, Zap, Rocket } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useState } from "react"

interface StrategySelectorProps {
  onSubmit: (strategy: "eco" | "balanced" | "quality") => void
}

export function StrategySelector({ onSubmit }: StrategySelectorProps) {
  const [selected, setSelected] = useState<"eco" | "balanced" | "quality">("balanced")
  const [taskMode, setTaskMode] = useState<"summarize" | "chat">("summarize")

  const strategies = [
    {
      id: "eco" as const,
      label: "Eco-Mode",
      icon: Leaf,
      description: "Minimize carbon footprint. Slower, highly efficient.",
      color: "from-green-600 to-green-700",
      textColor: "text-green-400",
    },
    {
      id: "balanced" as const,
      label: "Balanced Mode",
      icon: Zap,
      description: "Good quality & reasonable speed. Recommended.",
      color: "from-blue-600 to-blue-700",
      textColor: "text-blue-400",
    },
    {
      id: "quality" as const,
      label: "Max Quality",
      icon: Rocket,
      description: "Highest quality, fastest response. Highest footprint.",
      color: "from-purple-600 to-purple-700",
      textColor: "text-purple-400",
    },
  ]

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3, duration: 0.5 }}
      className="space-y-8"
    >
      {/* Task Mode Selection */}
      <Card className="p-6 bg-card/50 border-border/50">
        <h3 className="text-lg font-semibold mb-4">Primary Task</h3>
        <div className="flex gap-4">
          {["summarize", "chat"].map((mode) => (
            <motion.button
              key={mode}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setTaskMode(mode as "summarize" | "chat")}
              className={`px-6 py-2 rounded-lg font-medium transition-all ${
                taskMode === mode
                  ? "bg-primary text-primary-foreground"
                  : "bg-card border border-border/50 text-muted-foreground hover:border-border"
              }`}
            >
              {mode === "summarize" ? "Summarize" : "Prepare for Chat (RAG)"}
            </motion.button>
          ))}
        </div>
      </Card>

      {/* Processing Strategy Selection */}
      <Card className="p-6 bg-card/50 border-border/50">
        <h3 className="text-lg font-semibold mb-4">Processing Strategy</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {strategies.map((strategy, index) => {
            const Icon = strategy.icon
            const isSelected = selected === strategy.id

            return (
              <motion.button
                key={strategy.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                whileHover={{ y: -4 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => setSelected(strategy.id)}
                className={`p-4 rounded-lg border-2 transition-all ${
                  isSelected
                    ? `border-primary bg-gradient-to-br ${strategy.color}`
                    : "border-border/50 bg-background/30 hover:border-border"
                }`}
              >
                <Icon className={`w-6 h-6 mb-3 ${isSelected ? strategy.textColor : "text-muted-foreground"}`} />
                <p className={`font-semibold mb-1 ${isSelected ? "text-white" : "text-foreground"}`}>
                  {strategy.label}
                </p>
                <p className={`text-xs ${isSelected ? "text-white/80" : "text-muted-foreground"}`}>
                  {strategy.description}
                </p>
              </motion.button>
            )
          })}
        </div>
      </Card>

      <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
        <Button
          onClick={() => onSubmit(selected)}
          size="lg"
          className="w-full bg-primary hover:bg-primary/90 text-primary-foreground"
        >
          Start Job
        </Button>
      </motion.div>
    </motion.div>
  )
}
