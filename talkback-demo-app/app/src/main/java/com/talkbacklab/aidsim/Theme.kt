package com.talkbacklab.aidsim

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

object AidColors {
    val Background = Color(0xFF101014)
    val Surface = Color(0xFF1C1C22)
    val SurfaceHigh = Color(0xFF26262E)
    val Accent = Color(0xFF7C5CFF)
    val Left = Color(0xFF4FA3F7)
    val Right = Color(0xFFF06A6A)
    val Banner = Color(0xFFC0392B)
    val TextPrimary = Color(0xFFF2F2F5)
    val TextSecondary = Color(0xFF9A9AA6)
    val Connected = Color(0xFF4CD97B)
}

@Composable
fun AidSimTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            background = AidColors.Background,
            surface = AidColors.Surface,
            primary = AidColors.Accent,
            onBackground = AidColors.TextPrimary,
            onSurface = AidColors.TextPrimary
        ),
        content = content
    )
}
