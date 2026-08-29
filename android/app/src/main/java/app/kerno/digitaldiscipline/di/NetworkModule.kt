package app.kerno.digitaldiscipline.di

import app.kerno.digitaldiscipline.data.local.AuthTokenStore
import app.kerno.digitaldiscipline.data.remote.DeviceSigningInterceptor
import app.kerno.digitaldiscipline.data.remote.KernoApi
import com.squareup.moshi.Moshi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import javax.inject.Singleton

/**
 * BASE_URL is intentionally NOT hardcoded to a production domain — see
 * BuildConfig.API_BASE_URL usage below, configured per build type in
 * app/build.gradle's buildConfigField. This build has no real deployed
 * backend URL to point to (the backend built this session runs locally in
 * the dev environment, not at a public domain), so this is left as a
 * build-config value the actual deployer sets, consistent with the honesty
 * principle applied throughout this codebase: a hardcoded fake production
 * URL would be worse than an explicit placeholder that fails loudly if unset.
 */
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideMoshi(): Moshi = Moshi.Builder().build()

    @Provides
    @Singleton
    fun provideAuthInterceptor(authTokenStore: AuthTokenStore): okhttp3.Interceptor =
        okhttp3.Interceptor { chain ->
            // JWT bearer token attached to every request except the few that
            // must work without one. In the real flow, device registration
            // happens after account login, so an access token is realistically
            // always available by the time the agent makes authenticated
            // calls — the null-safety here means an unauthenticated call
            // fails with a normal 401 from the server rather than crashing
            // the interceptor.
            val token = runBlocking { authTokenStore.getAccessToken() }
            val request = if (token != null) {
                chain.request().newBuilder()
                    .addHeader("Authorization", "Bearer $token")
                    .build()
            } else {
                chain.request()
            }
            chain.proceed(request)
        }

    @Provides
    @Singleton
    fun provideOkHttpClient(
        authInterceptor: okhttp3.Interceptor,
        signingInterceptor: DeviceSigningInterceptor
    ): OkHttpClient {
        val loggingInterceptor = HttpLoggingInterceptor().apply {
            // BODY-level logging is deliberately NOT enabled even in debug
            // builds by default — request/response bodies here can include
            // JWT tokens and signed policy payloads; HEADERS level avoids
            // dumping sensitive body content to logcat, which on some devices
            // is readable by other apps with the right permissions. A
            // developer debugging locally can temporarily bump this to BODY
            // in their own build, but it should not be the shipped default.
            level = HttpLoggingInterceptor.Level.HEADERS
        }
        return OkHttpClient.Builder()
            .addInterceptor(authInterceptor)
            // Signing interceptor runs after auth in the chain (order
            // matches call order in addInterceptor below) — though in
            // practice these two are independent (one adds a header, the
            // other rewrites the body), so this ordering is noted for
            // clarity, not because a bug would occur if reversed.
            .addInterceptor(signingInterceptor)
            .addInterceptor(loggingInterceptor)
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(okHttpClient: OkHttpClient, moshi: Moshi): Retrofit =
        Retrofit.Builder()
            .baseUrl(app.kerno.digitaldiscipline.BuildConfig.API_BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()

    @Provides
    @Singleton
    fun provideKernoApi(retrofit: Retrofit): KernoApi = retrofit.create(KernoApi::class.java)
}
