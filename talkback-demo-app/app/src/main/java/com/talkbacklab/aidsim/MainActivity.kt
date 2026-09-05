package com.talkbacklab.aidsim

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.semantics.semantics

class MainActivity : ComponentActivity() {

    private var pending = mutableStateOf(AidState())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pending.value = AidState.fromIntent(intent)
        setContent {
            var state by pending
            AidSimTheme {
                AidSimScreen(
                    state = state,
                    onState = { state = it },
                    modifier = Modifier
                        .fillMaxSize()
                        .semantics { testTagsAsResourceId = true }
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        pending.value = AidState.fromIntent(intent)
    }
}
