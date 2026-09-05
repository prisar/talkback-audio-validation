package com.talkbacklab.aidsim

import kotlin.math.abs

enum class Side { LEFT, RIGHT }

object Labels {

    private fun sideWord(side: Side) = if (side == Side.LEFT) "Left" else "Right"

    private fun batteryValue(state: AidState, side: Side): Int {
        val base = when (effectiveSide(state, side)) {
            Side.LEFT -> state.leftBattery
            Side.RIGHT -> state.rightBattery
        }
        return if (state.defect == Defect.BATTERY_VALUE) {
            if (base >= 30) base - 30 else base + 30
        } else {
            base
        }
    }

    private fun volumeValue(state: AidState, side: Side): Int {
        val base = when (effectiveSide(state, side)) {
            Side.LEFT -> state.leftVolume
            Side.RIGHT -> state.rightVolume
        }
        return if (state.defect == Defect.VOLUME_SIGN) abs(base) else base
    }

    private fun connectedValue(state: AidState, side: Side): Boolean =
        when (effectiveSide(state, side)) {
            Side.LEFT -> state.leftConnected
            Side.RIGHT -> state.rightConnected
        }

    private fun effectiveSide(state: AidState, side: Side): Side =
        if (state.defect == Defect.SWAP_SIDES) {
            if (side == Side.LEFT) Side.RIGHT else Side.LEFT
        } else {
            side
        }

    private fun spokenNumber(value: Int): String =
        if (value < 0) "minus ${abs(value)}" else "$value"

    fun battery(state: AidState, side: Side): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        return "${sideWord(side)} hearing aid battery, ${batteryValue(state, side)} percent"
    }

    fun batteryChip(state: AidState, side: Side): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        return "${sideWord(side)} battery, ${batteryValue(state, side)} percent"
    }

    fun volume(state: AidState, side: Side): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        return "${sideWord(side)} volume, level ${spokenNumber(volumeValue(state, side))}"
    }

    fun connection(state: AidState, side: Side): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        val word = if (connectedValue(state, side)) "connected" else "disconnected"
        return "${sideWord(side)} hearing aid, $word"
    }

    fun program(state: AidState): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        return "Program, ${state.program}, selected"
    }

    fun masterVolume(state: AidState): String? {
        if (state.defect == Defect.MISSING_LABEL) return null
        val average = (state.leftVolume + state.rightVolume) / 2
        return "Volume, level ${spokenNumber(average)}"
    }

    fun displayNumber(value: Int): String = "$value"
}
