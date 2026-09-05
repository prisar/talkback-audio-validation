package com.talkbacklab.aidsim

import android.content.Intent

enum class Defect {
    NONE, BATTERY_VALUE, SWAP_SIDES, VOLUME_SIGN, MISSING_LABEL;

    companion object {
        fun from(raw: String?): Defect = when (raw?.lowercase()) {
            "battery_value" -> BATTERY_VALUE
            "swap_sides" -> SWAP_SIDES
            "volume_sign" -> VOLUME_SIGN
            "missing_label" -> MISSING_LABEL
            else -> NONE
        }
    }
}

data class AidState(
    val program: String = "Universal",
    val programDescription: String = "Personal program adapting to your environment.",
    val leftVolume: Int = 0,
    val rightVolume: Int = 0,
    val leftBattery: Int = 100,
    val rightBattery: Int = 100,
    val leftConnected: Boolean = true,
    val rightConnected: Boolean = true,
    val defect: Defect = Defect.NONE
) {
    companion object {
        const val VOLUME_MIN = -6
        const val VOLUME_MAX = 6

        private fun intExtra(intent: Intent, key: String, fallback: Int): Int {
            intent.getStringExtra(key)?.trim()?.toIntOrNull()?.let { return it }
            return intent.getIntExtra(key, fallback)
        }

        fun fromIntent(intent: Intent?): AidState {
            val d = AidState()
            if (intent == null) return d
            return AidState(
                program = intent.getStringExtra("program") ?: d.program,
                programDescription = intent.getStringExtra("program_description")
                    ?: descriptionFor(intent.getStringExtra("program") ?: d.program),
                leftVolume = intExtra(intent, "left_volume", d.leftVolume)
                    .coerceIn(VOLUME_MIN, VOLUME_MAX),
                rightVolume = intExtra(intent, "right_volume", d.rightVolume)
                    .coerceIn(VOLUME_MIN, VOLUME_MAX),
                leftBattery = intExtra(intent, "left_battery", d.leftBattery).coerceIn(0, 100),
                rightBattery = intExtra(intent, "right_battery", d.rightBattery).coerceIn(0, 100),
                leftConnected = intent.getBooleanExtra("left_connected", d.leftConnected),
                rightConnected = intent.getBooleanExtra("right_connected", d.rightConnected),
                defect = Defect.from(intent.getStringExtra("defect"))
            )
        }

        private fun descriptionFor(program: String): String = when (program) {
            "Noisy Environment" -> "Reduces background noise in busy places."
            "Restaurant" -> "Focuses on speech in front of you."
            "Music" -> "Widens the range for listening to music."
            else -> "Personal program adapting to your environment."
        }
    }
}
